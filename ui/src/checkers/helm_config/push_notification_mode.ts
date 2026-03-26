/**
 * Reports the auto-detected push notification mode.
 *
 * Classifies into one of three options from Julia's documentation:
 * - Option A: Wire-managed SNS/SQS relay (recommended)
 * - Option B: Customer-managed SNS/SQS relay (requires custom client builds)
 * - Option C: WebSocket-only / fake-aws (no iOS push, Android battery drain)
 *
 * Includes the decision guide context and cross-references with internet
 * availability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class PushNotificationModeChecker extends BaseChecker {
    readonly path: string = 'helm_config/push_notification_mode'
    readonly name: string = 'Push notification mode'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = (
        'Detects the push notification configuration: '
        + '**Option A** (Wire-managed SNS/SQS — recommended), '
        + '**Option B** (customer-managed SNS/SQS — requires custom client builds), or '
        + '**Option C** (WebSocket-only via fake-aws — no iOS push, Android battery drain).'
    )

    check(data: DataLookup): CheckResult {
        const point = data.get('config/gundeck_push_config')

        if (!point || !point.value) {
            return {
                status: 'gather_failure',
                status_reason: 'Gundeck push config data was not collected.',
                recommendation: 'Ensure the config/gundeck_push_config target runs successfully.',
            }
        }

        let parsed: unknown
        try { parsed = JSON.parse(String(point.value)) } catch { parsed = null }
        if (!parsed || typeof parsed !== 'object') {
            return {
                status: 'gather_failure',
                status_reason: 'Could not parse gundeck push config data.',
                raw_output: point.raw_output,
            }
        }

        const config_data = parsed as Record<string, unknown>
        const is_fake_aws: boolean = config_data.is_fake_aws as boolean ?? true
        const sns_endpoint: string = (config_data.sns_endpoint as string) ?? ''
        const sqs_endpoint: string = (config_data.sqs_endpoint as string) ?? ''
        const account: string = (config_data.account as string) ?? ''

        const has_internet: boolean = data.config?.options?.has_internet ?? true

        // ── Option C: WebSocket-only (fake-aws) ──

        if (is_fake_aws) {
            // Check that fake-aws pods are running
            const fake_pods_point = data.get('config/fake_aws_pods')
            let fake_pods_ok: boolean = true
            if (fake_pods_point?.value) {
                let fake_data: Record<string, unknown> | null = null
                try { fake_data = JSON.parse(String(fake_pods_point.value)) as Record<string, unknown> } catch { /* ignore */ }
                if (fake_data) {
                    const sns_running: boolean = fake_data.fake_sns_running as boolean ?? false
                    const sqs_running: boolean = fake_data.fake_sqs_running as boolean ?? false
                    fake_pods_ok = sns_running && sqs_running
                }
            }

            if (!fake_pods_ok) {
                return {
                    status: 'unhealthy',
                    status_reason: '**Option C (WebSocket-only)** detected, but **fake-aws pods are not running**. Gundeck requires fake-aws-sns and fake-aws-sqs pods for internal event processing even in WebSocket-only mode.',
                    fix_hint: '1. Check fake-aws pod status:\n   ```\n   kubectl get pods -n wire | grep fake-aws\n   ```\n2. If not deployed, install the fake-aws helm chart:\n   ```\n   helm install fake-aws charts/fake-aws\n   ```',
                    display_value: 'Option C (fake-aws pods missing)',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: (
                    '**Option C: WebSocket-only** (fake-aws).\n\n'
                    + '- Mobile push notifications (FCM/APNS) are **not available**.\n'
                    + '- **Android** clients can receive notifications via persistent WebSocket. '
                    + 'Users must enable **"Keep connection to WebSocket on"** in the Wire Android app '
                    + 'under **Settings → Network Settings**. This causes significantly higher battery drain.\n'
                    + '- **iOS** clients will **only** receive notifications while the Wire app is actively open. '
                    + 'There is no WebSocket-only mode for iOS.'
                ),
                display_value: 'Option C (WebSocket-only)',
                raw_output: point.raw_output,
            }
        }

        // ── Option A or B: Real AWS ──

        if (!has_internet) {
            return {
                status: 'unhealthy',
                status_reason: (
                    'Gundeck is configured for **real AWS** push notifications (Option A or B), '
                    + 'but this deployment is declared as **offline** (no internet). '
                    + 'AWS SNS/SQS endpoints will be unreachable.'
                ),
                fix_hint: (
                    '**If this is an offline deployment**, switch to Option C (WebSocket-only):\n'
                    + '- Install the fake-aws helm chart\n'
                    + '- Update gundeck config to point to fake-aws endpoints\n\n'
                    + '**If this deployment does have internet**, enable the "Internet Access" setting in the configuration.'
                ),
                display_value: 'real AWS (offline — inconsistent)',
                raw_output: point.raw_output,
            }
        }

        // Check for placeholder account ID
        const is_placeholder_account: boolean = (
            account === '123456789012' || account === '000000000000' || account === ''
        )

        let status_text: string = (
            `**Option A or B: Real AWS** (FCM/APNS push notifications enabled).\n\n`
            + `- SNS endpoint: \`${sns_endpoint}\`\n`
            + `- SQS endpoint: \`${sqs_endpoint}\`\n`
            + `- AWS Account: \`${account || 'not set'}\`\n\n`
        )

        if (is_placeholder_account) {
            status_text += (
                '**Warning:** The AWS account ID looks like a placeholder value. '
                + 'Verify that Wire has supplied you with real AWS credentials for push notification proxying.\n\n'
            )
        }

        // Add contract/option context
        status_text += (
            'Ensure you have a Wire contract covering push notification proxying (**Option A**, recommended). '
            + 'If you are maintaining your own AWS SNS/SQS infrastructure (**Option B**), note that this '
            + 'requires Wire to produce and maintain custom iOS and Android client builds on your behalf.'
        )

        return {
            status: is_placeholder_account ? 'warning' : 'healthy',
            status_reason: status_text,
            display_value: is_placeholder_account ? 'real AWS (placeholder account)' : 'Option A/B (real AWS)',
            raw_output: point.raw_output,
        }
    }
}

export default PushNotificationModeChecker
