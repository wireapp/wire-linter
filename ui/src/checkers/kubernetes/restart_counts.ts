/**
 * Detects when pods are restarting too often.
 *
 * Looks at the restart_counts target which gives us a number, a string,
 * or a boolean. If it says pods are restarting a lot, that usually means
 * they're crashing or running out of memory, so we flag it as a warning.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class RestartCountsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/restart_counts'
    readonly name: string = 'Pod restart counts'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors **pod restart counts** across the cluster. Frequent restarts indicate crashlooping services, memory leaks, or misconfiguration that can degrade reliability.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pods/restart_counts')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Pod restart counts data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/pods/restart_counts\n   ```\n3. Manually check: `kubectl get pods -A --sort-by=.status.containerStatuses[0].restartCount`',
                recommendation: 'Pod restart counts data not collected.',
            }
        }

        // Null value means the target ran but produced no usable data
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Pod restart counts data was collected but has no value.',
                recommendation: 'Pod restart counts data not available.',
            }
        }

        const value: string | number | boolean = point.value as string | number | boolean
        const warning_fix_hint: string =
            '1. Identify pods with high restart counts:\n   ```\n   kubectl get pods -A --sort-by=.status.containerStatuses[0].restartCount\n   ```\n2. Check the events and status of restarting pods:\n   ```\n   kubectl describe pod <name> -n <namespace>\n   ```\n3. Check container logs (including previous crash):\n   ```\n   kubectl logs <name> -n <namespace> --previous\n   ```\n4. Common causes:\n   - **OOMKilled**: container exceeding memory limits (increase `resources.limits.memory`)\n   - **CrashLoopBackOff**: application error on startup (check logs)\n   - **Liveness probe failure**: probe misconfigured or app too slow to respond\n5. Check if the pod was OOMKilled:\n   ```\n   kubectl get pod <name> -n <namespace> -o jsonpath=\'{.status.containerStatuses[*].lastState.terminated.reason}\'\n   ```'

        // Numeric value any positive count is concerning
        if (typeof value === 'number') {
            if (value > 0) {
                return {
                    status: 'warning',
                    status_reason: 'Pod restart count is **{{value}}**, indicating possible crashloop or OOM conditions.',
                    fix_hint: warning_fix_hint,
                    recommendation: 'Pods with high restart counts detected. High restarts indicate crashloop or OOM conditions.',
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { value },
                }
            }

            return {
                status: 'healthy',
                status_reason: 'Pod restart count is **{{value}}**, no excessive restarts detected.',
                display_value: value,
                raw_output: point.raw_output,
                template_data: { value },
            }
        }

        // Boolean true means no high restarts, false means high restarts detected
        if (typeof value === 'boolean') {
            if (!value) {
                return {
                    status: 'warning',
                    status_reason: 'High pod restart counts were flagged (boolean **false**).',
                    fix_hint: warning_fix_hint,
                    recommendation: 'Pods with high restart counts detected. High restarts indicate crashloop or OOM conditions.',
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'No high pod restart counts detected (boolean **true**).',
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // String value check for indicators of high restarts
        const lower_value: string = value.toLowerCase()

        // "none", empty, or "0" indicate no problems
        if (lower_value === 'none' || lower_value === '0' || lower_value.trim() === '') {
            return {
                status: 'healthy',
                status_reason: 'Restart counts value "{{value}}" indicates no excessive restarts.',
                display_value: value,
                raw_output: point.raw_output,
                template_data: { value },
            }
        }

        // Check if the string contains "high" or any number greater than 10
        const has_high_keyword: boolean = lower_value.includes('high')

        // Try context-aware extraction first: number immediately before "restart"
        const restart_context_match: RegExpMatchArray | null = value.match(/(\d+)\s*restart/i)
        // Fall back to the largest number in the string if no restart-adjacent number found
        const all_numbers: RegExpMatchArray | null = value.match(/\d+/g)
        const largest_number: number | null = all_numbers
            ? Math.max(...all_numbers.map((n: string) => parseInt(n, 10)))
            : null
        const extracted_count: number | null = restart_context_match?.[1]
            ? parseInt(restart_context_match[1], 10)
            : largest_number
        const has_high_number: boolean = extracted_count !== null && extracted_count > 10

        if (has_high_keyword || has_high_number) {
            return {
                status: 'warning',
                status_reason: 'Restart counts value "{{value}}" indicates high restart activity.',
                fix_hint: warning_fix_hint,
                recommendation: 'Pods with high restart counts detected. High restarts indicate crashloop or OOM conditions.',
                display_value: value,
                raw_output: point.raw_output,
                template_data: { value },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Restart counts value "{{value}}" does not indicate excessive restarts.',
            display_value: value,
            raw_output: point.raw_output,
            template_data: { value },
        }
    }
}

export default RestartCountsChecker
