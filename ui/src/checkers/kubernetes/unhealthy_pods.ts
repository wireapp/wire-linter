/**
 * Looks for pods that aren't Running or Completed.
 *
 * Uses the kubernetes/pods/unhealthy_count metric. If that number is above
 * zero, something's broken either pod startup failed or scheduling is stuck.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class UnhealthyPodsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/unhealthy_pods'
    readonly name: string = 'Unhealthy pods'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Detects pods that are not in **Running** or **Completed** state. Unhealthy pods indicate failed deployments, scheduling problems, or image pull errors that prevent services from operating.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pods/unhealthy_count')

        // No data means we couldn't gather the unhealthy pod count
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Unhealthy pod count data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/pods/unhealthy_count\n   ```\n3. Manually check:\n   ```\n   kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded\n   ```',
                recommendation: 'Couldn\'t collect unhealthy pod data.',
            }
        }

        // Command ran but returned no value (collection failure)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Unhealthy pod count value was null.',
                recommendation: 'The command ran but did not return a usable value.',
                raw_output: point.raw_output,
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Unhealthy pod count could not be parsed as a number.',
                recommendation: 'The collected unhealthy pod count was not in a recognizable numeric format.',
                raw_output: point.raw_output,
            }
        }

        // If there are any unhealthy pods, that's a problem
        if (count > 0) {
            return {
                status: 'unhealthy',
                status_reason: '**{{count}}** pod(s) are not in Running or Completed state.',
                fix_hint: '1. List unhealthy pods:\n   ```\n   kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded\n   ```\n2. Check pod events: `kubectl describe pod <name> -n <namespace>`\n3. Check container logs: `kubectl logs <name> -n <namespace> --previous`\n4. Common causes:\n   - **ImagePullBackOff**: wrong image name or registry credentials\n   - **CrashLoopBackOff**: application crashes on startup (check logs)\n   - **Pending**: insufficient resources or node affinity mismatch\n   - **Evicted**: node under disk/memory pressure\n5. For scheduling issues: `kubectl get events -A --sort-by=.lastTimestamp | tail -20`',
                recommendation: `${count} pod(s) not in Running/Completed state. Check with <command>kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded</command>`,
                display_value: count,
                raw_output: point.raw_output,
                template_data: { count },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All pods are in **Running** or **Completed** state.',
            display_value: count,
            raw_output: point.raw_output,
        }
    }
}

export default UnhealthyPodsChecker
