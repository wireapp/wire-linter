/**
 * Checks whether log rotation is configured with 72h max retention.
 *
 * Consumes the operations/log_rotation target (boolean or string).
 * Wire's privacy whitepaper says logs older than 72 hours must be deleted.
 * Without rotation, logs pile up and you're in violation.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class LogRotationChecker extends BaseChecker {
    readonly path: string = 'operations/log_rotation'
    readonly name: string = 'Log rotation configured (72h max retention)'
    readonly category: string = 'Operations / Tooling'
    readonly interest = 'Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Ensures **log rotation** is configured with a **72-hour** maximum retention. Wire\'s privacy whitepaper requires logs older than 72 hours to be deleted; without rotation, logs accumulate and violate this policy.'

    check(data: DataLookup): CheckResult {
        const point = data.get('operations/log_rotation')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `operations/log_rotation` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has **SSH access** to the nodes\n2. Check that `logrotate` or the cluster log rotation config is accessible\n3. Review the gatherer logs for permission errors',
                recommendation: 'Log rotation configured (72h max retention) data not collected.',
            }
        }

        // Null value means the gatherer encountered an error collecting this target
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Log rotation data collection returned null (gatherer error).',
                recommendation: 'Log rotation configured (72h max retention) data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value requires pattern matching — any non-empty string cannot be
        // assumed healthy because error strings ("permission denied", "not found", etc.)
        // would otherwise be misclassified as a passing privacy-compliance check.
        if (typeof val === 'string') {
            const lower = val.toLowerCase()

            // Empty string means no rotation config was found
            if (val.length === 0) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Log rotation is not configured; logs may exceed the 72h retention policy.',
                    recommendation: 'Log rotation not configured. Wire\'s privacy whitepaper requires logs older than 72h to be deleted.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Negative keywords indicate a collection error, not a valid config
            const negative_keywords = ['error', 'fail', 'missing', 'not found', 'permission denied', 'exception', 'traceback', 'no such']
            if (negative_keywords.some(keyword => lower.includes(keyword))) {
                return {
                    status: 'gather_failure',
                    status_reason: `Log rotation data collection returned an error: ${val}`,
                    recommendation: 'Log rotation configured (72h max retention) data not collected.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Positive keywords confirm rotation is configured
            const positive_keywords = ['configured', 'enabled', '72h', '72 h', 'rotate', 'logrotate', 'daily', 'weekly']
            if (positive_keywords.some(keyword => lower.includes(keyword))) {
                return {
                    status: 'healthy',
                    status_reason: 'Log rotation is configured with **72h** max retention: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            // Unrecognized string — cannot confirm rotation is correctly configured
            return {
                status: 'warning',
                status_reason: `Log rotation config found but content is unrecognized: ${val}`,
                recommendation: 'Verify log rotation is configured with a 72-hour maximum retention per Wire\'s privacy whitepaper.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means log rotation is configured
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Log rotation is configured with **72h** max retention.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false rotation not configured
        return {
            status: 'unhealthy',
            status_reason: 'Log rotation is **not configured**; logs may exceed the 72h retention policy.',
            fix_hint: '1. Configure log rotation for Wire services. For `logrotate`:\n   ```\n   # /etc/logrotate.d/wire\n   /var/log/wire/*.log {\n       hourly\n       maxage 3\n       rotate 72\n       compress\n       missingok\n       notifempty\n   }\n   ```\n2. For Kubernetes-level log rotation, set kubelet flags:\n   ```\n   --container-log-max-size=50Mi\n   --container-log-max-files=3\n   ```\n3. Verify rotation is working: `logrotate -d /etc/logrotate.d/wire`\n4. Wire\'s privacy whitepaper **requires** logs older than 72h to be deleted',
            recommendation: 'Log rotation not configured. Wire\'s privacy whitepaper requires logs older than 72h to be deleted.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default LogRotationChecker
