/**
 * Checks whether the SMTP/email service is running.
 *
 * Consumes the operations/smtp_service target (boolean or string).
 * Without SMTP, account verification emails and password resets go nowhere.
 * Users get silently locked out.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class SmtpServiceChecker extends BaseChecker {
    readonly path: string = 'operations/smtp_service'
    readonly name: string = 'SMTP/email service running'
    readonly category: string = 'Operations / Tooling'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **SMTP/email service** is running. Without it, account verification emails and password resets fail silently, **locking users out** of their accounts.'

    check(data: DataLookup): CheckResult {
        const point = data.get('operations/smtp_service')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `operations/smtp_service` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can reach the SMTP service endpoint\n2. Check that the SMTP pod is running: `kubectl get pods -n wire -l app=smtp`\n3. Review the gatherer logs for connection errors or DNS resolution failures',
                recommendation: 'SMTP/email service running data not collected.',
            }
        }

        // Collection ran but the command failed (e.g. SSH timeout)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'SMTP/email service data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'SMTP service target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value non-empty means SMTP is running
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'SMTP/email service is **running**: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'SMTP/email service is **not running**.',
                fix_hint: '1. Check the SMTP pod status: `kubectl get pods -n wire -l app=smtp`\n2. Review SMTP pod logs: `kubectl logs -n wire -l app=smtp --tail=50`\n3. Verify SMTP credentials in the helm values are correct\n4. Test SMTP connectivity manually:\n   ```\n   kubectl run smtp-test --rm -it --image=busybox -- sh -c "echo test | nc <smtp-host> 25"\n   ```\n5. Check that the SMTP secret exists: `kubectl get secret -n wire smtp-credentials`',
                recommendation: 'SMTP/email service not running. Account verification and password resets won\'t work.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means SMTP is running
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'SMTP/email service is **running**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false SMTP not running
        return {
            status: 'unhealthy',
            status_reason: 'SMTP/email service is **not running**.',
            fix_hint: '1. Check the SMTP pod status: `kubectl get pods -n wire -l app=smtp`\n2. Review SMTP pod logs: `kubectl logs -n wire -l app=smtp --tail=50`\n3. Verify SMTP credentials in the helm values are correct\n4. Test SMTP connectivity manually:\n   ```\n   kubectl run smtp-test --rm -it --image=busybox -- sh -c "echo test | nc <smtp-host> 25"\n   ```\n5. Check that the SMTP secret exists: `kubectl get secret -n wire smtp-credentials`',
            recommendation: 'SMTP/email service not running. Account verification and password resets won\'t work.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default SmtpServiceChecker
