/**
 * Shows how many pods are currently running in the cluster.
 *
 * Gets the data from kubernetes/pods/total_running. Just displays the
 * count it doesn't really pass or fail anything.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class TotalRunningPodsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/total_running_pods'
    readonly name: string = 'Total running pods'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Reports the total number of **running pods** in the cluster. Provides a baseline count to spot unexpected drops in capacity or verify that all expected workloads are scheduled.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pods/total_running')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Total running pods data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/pods/total_running\n   ```\n3. Manually check: `kubectl get pods -A --field-selector=status.phase=Running | wc -l`',
                recommendation: 'Total running pods data not collected.',
            }
        }

        // Command ran but returned no value
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Total running pods value was null.',
                recommendation: 'The command ran but did not return a usable value.',
                raw_output: point.raw_output,
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Total running pods value could not be parsed as a number.',
                recommendation: 'The collected pod count data was not in a recognizable numeric format.',
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: '**{{count}}** pod(s) are currently running in the cluster.',
            display_value: count,
            display_unit: 'pods',
            raw_output: point.raw_output,
            template_data: { count },
        }
    }
}

export default TotalRunningPodsChecker
