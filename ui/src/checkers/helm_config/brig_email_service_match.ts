/**
 * Verifies brig's email configuration matches the running email service.
 *
 * Cross-references brig's SMTP/SES config with the actual email pods running
 * in the cluster. Detects misconfigurations like brig pointing to demo-smtp
 * when no demo-smtp pod exists, or using SES without internet access.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class BrigEmailServiceMatchChecker extends BaseChecker {
    readonly path: string = 'helm_config/brig_email_service_match'
    readonly name: string = 'Email delivery configuration'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that brig\'s email delivery configuration (SMTP or AWS SES) matches the actual running services. Email is required for password resets, account verification, and team invitations.'

    check(data: DataLookup): CheckResult {
        const email_point = data.get('config/brig_email_config')

        if (!email_point?.value) {
            return {
                status: 'gather_failure',
                status_reason: 'Brig email config data was not collected.',
            }
        }

        let email_data: Record<string, unknown> | null = null
        try { email_data = JSON.parse(String(email_point.value)) as Record<string, unknown> } catch { /* ignore */ }

        if (!email_data) {
            return {
                status: 'gather_failure',
                status_reason: 'Could not parse brig email config data.',
                raw_output: email_point.raw_output,
            }
        }

        const mode: string = (email_data.mode as string) ?? 'unknown'
        const smtp_host: string = (email_data.smtp_host as string) ?? ''
        const smtp_port: number = (email_data.smtp_port as number) ?? 0
        const smtp_conn_type: string = (email_data.smtp_conn_type as string) ?? ''
        const email_sender: string = (email_data.email_sender as string) ?? ''

        // Check for placeholder email sender
        const sender_is_placeholder: boolean = !email_sender || email_sender.includes('example.com')

        if (mode === 'ses') {
            // SES mode — check internet
            const has_internet: boolean = data.config?.options?.has_internet ?? true
            if (!has_internet) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Brig uses **AWS SES** for email but the deployment is declared as **offline**. SES requires internet connectivity.',
                    fix_hint: 'Either enable internet access or switch to SMTP by configuring `brig.config.smtp.host` in helm values.',
                    display_value: 'SES (offline — broken)',
                    raw_output: email_point.raw_output,
                }
            }

            let result_reason: string = 'Email delivery: **AWS SES**.'
            if (sender_is_placeholder) {
                result_reason += ' **Warning:** email sender looks like a placeholder (`{{sender}}`).'
            }

            return {
                status: sender_is_placeholder ? 'warning' : 'healthy',
                status_reason: result_reason,
                display_value: 'AWS SES',
                raw_output: email_point.raw_output,
                template_data: { sender: email_sender },
            }
        }

        // SMTP mode
        if (!smtp_host) {
            return {
                status: 'unhealthy',
                status_reason: 'No SMTP host configured in brig. Email delivery is **not working** — password resets and account verification will fail.',
                fix_hint: '1. Set `brig.config.smtp.host` in your wire-server helm values\n2. Set `brig.config.smtp.port` and `brig.config.smtp.connType`\n3. Redeploy wire-server',
                display_value: 'not configured',
                raw_output: email_point.raw_output,
            }
        }

        // Check if it's the demo SMTP service
        const is_demo: boolean = smtp_host === 'smtp' || smtp_host === 'demo-smtp'

        if (is_demo) {
            // Check if the demo-smtp pod is running
            const smtp_service_point = data.get('operations/smtp_service')
            const smtp_running: boolean = smtp_service_point?.value === true || smtp_service_point?.value === 'true'

            if (!smtp_running) {
                return {
                    status: 'unhealthy',
                    status_reason: `Brig is configured to use demo SMTP at \`${smtp_host}\` but no demo-smtp pod is running.`,
                    fix_hint: '1. Install the demo-smtp chart:\n   ```\n   helm install smtp wire/demo-smtp -f values/demo-smtp/values.yaml\n   ```\n2. Or configure a real SMTP server in brig.',
                    display_value: `demo-smtp (not running)`,
                    raw_output: email_point.raw_output,
                }
            }

            let demo_reason: string = `Email delivery: **demo SMTP** (\`${smtp_host}\`). This is a mock service that accepts but does **not deliver** real emails. Password resets and verification emails will not be sent.`
            if (sender_is_placeholder) {
                demo_reason += ` Email sender is a placeholder: \`${email_sender}\`.`
            }

            return {
                status: 'warning',
                status_reason: demo_reason,
                display_value: 'demo-smtp (no delivery)',
                raw_output: email_point.raw_output,
            }
        }

        // External SMTP server
        let ext_reason: string = `Email delivery: **SMTP** (\`${smtp_host}:${smtp_port}\`, ${smtp_conn_type || 'unknown encryption'}).`
        if (sender_is_placeholder) {
            ext_reason += ` **Warning:** email sender looks like a placeholder (\`${email_sender}\`).`
        }

        return {
            status: sender_is_placeholder ? 'warning' : 'healthy',
            status_reason: ext_reason,
            display_value: `SMTP (${smtp_host})`,
            raw_output: email_point.raw_output,
        }
    }
}

export default BrigEmailServiceMatchChecker
