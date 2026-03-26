/**
 * Makes sure brig's SMTP connection is encrypted not sending credentials and
 * email content in plain text.
 *
 * We look at the brig ConfigMap and find emailSMS.email.smtpConnType. If it's
 * set to «plain», that means email credentials and all your message content are
 * just floating across the network unencrypted. That's not great.
 */

// External
import yaml from 'js-yaml'

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class BrigSmtpSecurityChecker extends BaseChecker {
    readonly path: string = 'helm_config/brig_smtp_security'
    readonly name: string = 'SMTP connection uses encryption'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that Brig\'s SMTP connection uses **TLS** or **STARTTLS** encryption. Sending email credentials and message content over a plain-text connection exposes them to **network interception**.'

    check(data: DataLookup): CheckResult {
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
                status_reason: 'Could not parse **Brig** ConfigMap YAML to check SMTP settings.',
                fix_hint: '1. Inspect the raw ConfigMap for YAML syntax errors:\n   ```\n   kubectl get configmap brig -n wire -o yaml\n   ```\n2. Fix any YAML formatting issues in the `brig` ConfigMap data.',
                recommendation: 'Could not parse Brig ConfigMap YAML to check SMTP settings.',
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

        // Dig down to find the SMTP connection type setting
        const email_sms = parsed.emailSMS as Record<string, unknown> | undefined
        const email = email_sms?.email as Record<string, unknown> | undefined
        const conn_type: string = String(email?.smtpConnType ?? '').toLowerCase()

        // If nothing's set, something's missing from the config
        if (!conn_type.trim()) {
            return {
                status: 'warning',
                status_reason: 'No SMTP connection type (`smtpConnType`) is configured in Brig.',
                fix_hint: '1. Set `emailSMS.email.smtpConnType` to `tls` or `starttls` in your helm values\n2. Apply the change:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```\n3. Verify:\n   ```\n   kubectl get configmap brig -n wire -o yaml | grep smtpConnType\n   ```',
                recommendation: 'No SMTP connection type configured in Brig.',
                display_value: 'not set',
                raw_output: point.raw_output,
            }
        }

        // «plain» means no encryption that's a problem
        if (conn_type === 'plain') {
            return {
                status: 'warning',
                status_reason: 'SMTP connection type is set to `plain` (**unencrypted**).',
                fix_hint: '1. Change `emailSMS.email.smtpConnType` from `plain` to `tls` or `starttls` in your helm values\n2. Apply the change:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```\n3. Verify the ConfigMap was updated:\n   ```\n   kubectl get configmap brig -n wire -o yaml | grep smtpConnType\n   ```',
                recommendation: 'SMTP is set to «plain» which means no encryption at all. Your email credentials and message content are just going over the wire in the clear. Switch to «tls» or «starttls» to encrypt the SMTP connection.',
                display_value: 'plain (unencrypted)',
                raw_output: point.raw_output,
            }
        }

        // «tls» or «starttls» both work connection's encrypted
        return {
            status: 'healthy',
            status_reason: 'SMTP connection type is set to `{{conn_type}}` (**encrypted**).',
            display_value: conn_type,
            raw_output: point.raw_output,
            template_data: { conn_type },
        }
    }
}

export default BrigSmtpSecurityChecker
