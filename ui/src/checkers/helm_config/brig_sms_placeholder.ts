/**
 * Makes sure the SMS sender in brig isn't just a placeholder that nobody filled in.
 *
 * We pull the brig ConfigMap from Kubernetes and parse the YAML looking for
 * emailSMS.general.smsSender. If it's a placeholder (like «insert-sms-sender»), that
 * means SMS verification and activation for new users will fail silently they'll
 * think it's processing but nothing actually happens.
 */

// External
import yaml from 'js-yaml'

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// These are the patterns people tend to use when they just left something as a placeholder
const _PLACEHOLDER_PATTERNS: string[] = [
    'insert-sms-sender',
    'placeholder',
    'change-me',
    'todo',
    'xxx',
    'example',
]

export class BrigSmsPlaceholderChecker extends BaseChecker {
    readonly path: string = 'helm_config/brig_sms_placeholder'
    readonly name: string = 'SMS sender configured (not placeholder)'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Detects **placeholder values** left in the SMS sender configuration. If the sender ID is still a placeholder, SMS-based user verification and activation will **fail silently**.'

    check(data: DataLookup): CheckResult {
        // Skip when SMS is not part of this deployment
        if (data.config && !data.config.options.expect_sms) {
            return {
                status: 'not_applicable',
                status_reason: 'SMS sending is not enabled in the deployment settings - check skipped.',
                display_value: 'skipped',
                recommendation: 'SMS sending is not enabled in the deployment settings - check skipped.',
            }
        }

        const point = data.get('kubernetes/configmaps/brig')

        // We need the brig ConfigMap to proceed
        if (!point || !point.value) {
            return {
                status: 'gather_failure',
                status_reason: 'Brig ConfigMap data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Kubernetes access:\n   ```\n   kubectl get configmap brig -n wire -o yaml\n   ```\n2. Re-run the gatherer ensuring the `kubernetes/configmaps/brig` target succeeds.',
                recommendation: 'Brig ConfigMap data not collected.',
            }
        }

        const raw_yaml: string = String(point.value)
        let parsed: Record<string, unknown>

        try {
            parsed = yaml.load(raw_yaml) as Record<string, unknown>
        } catch {
            return {
                status: 'gather_failure',
                status_reason: 'Could not parse **Brig** ConfigMap YAML to check SMS sender.',
                fix_hint: '1. Inspect the raw ConfigMap for YAML syntax errors:\n   ```\n   kubectl get configmap brig -n wire -o yaml\n   ```\n2. Fix any YAML formatting issues in the `brig` ConfigMap data.',
                recommendation: 'Could not parse Brig ConfigMap YAML to check SMS sender.',
                raw_output: point.raw_output,
            }
        }

        if (!parsed || typeof parsed !== 'object') {
            return {
                status: 'warning',
                status_reason: 'Brig ConfigMap parsed to an **empty document**.',
                fix_hint: '1. Check that the Brig ConfigMap has actual content:\n   ```\n   kubectl get configmap brig -n wire -o yaml\n   ```\n2. If the ConfigMap is empty, redeploy with correct helm values:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
                recommendation: 'Brig ConfigMap parsed to empty document.',
                raw_output: point.raw_output,
            }
        }

        // Dig into the config to find the SMS sender setting
        const email_sms = parsed.emailSMS as Record<string, unknown> | undefined
        const general = email_sms?.general as Record<string, unknown> | undefined
        const sms_sender: string = String(general?.smsSender ?? '')

        // If there's nothing there at all, SMS isn't set up
        if (!sms_sender.trim()) {
            return {
                status: 'warning',
                status_reason: 'No SMS sender is configured in Brig (`smsSender` is empty).',
                fix_hint: '1. Set `emailSMS.general.smsSender` to your Twilio or SMS provider sender ID in your helm values\n2. Apply the change:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```\n3. Verify the ConfigMap was updated:\n   ```\n   kubectl get configmap brig -n wire -o yaml | grep smsSender\n   ```',
                recommendation: 'No SMS sender configured in Brig. SMS-based verification and activation will not work.',
                display_value: 'not set',
                raw_output: point.raw_output,
            }
        }

        // Now check if it looks like a placeholder
        const sender_lower: string = sms_sender.toLowerCase()
        const is_placeholder: boolean = _PLACEHOLDER_PATTERNS.some(
            (pattern) => sender_lower.includes(pattern),
        )

        if (is_placeholder) {
            return {
                status: 'warning',
                status_reason: 'SMS sender is set to a **placeholder** value: `{{sms_sender}}`.',
                fix_hint: '1. Replace the placeholder `{{sms_sender}}` with your real Twilio or SMS provider sender ID in your helm values under `emailSMS.general.smsSender`\n2. Apply the change:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```\n3. Verify the ConfigMap was updated:\n   ```\n   kubectl get configmap brig -n wire -o yaml | grep smsSender\n   ```',
                recommendation: `SMS sender is still set to a placeholder: "${sms_sender}". Users won't be able to verify via SMS - the requests will fail silently. You need to put in a real Twilio or SMS provider sender ID.`,
                display_value: `placeholder: ${sms_sender}`,
                raw_output: point.raw_output,
                template_data: { sms_sender },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'SMS sender is configured with a valid value: `{{sms_sender}}`.',
            display_value: sms_sender,
            raw_output: point.raw_output,
            template_data: { sms_sender },
        }
    }
}

export default BrigSmsPlaceholderChecker
