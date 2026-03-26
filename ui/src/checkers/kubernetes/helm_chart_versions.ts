/**
 * Shows you the Helm chart versions for all releases in your cluster.
 *
 * Just pulls from the helm/releases data and displays what you've got.
 * Always comes back healthy since we're just reporting what's there.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class HelmChartVersionsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/helm_chart_versions'
    readonly name: string = 'Helm chart versions for all releases'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports **Helm chart versions** for all releases in the cluster. Provides an inventory of deployed chart versions to verify consistency and identify outdated or mismatched releases.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('helm/releases') ?? data.get('direct/helm/releases')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Helm chart versions data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API and `helm` is configured.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target helm/releases\n   ```\n3. Manually list Helm releases: `helm list -A`',
                recommendation: 'Helm chart versions for all releases data not collected.',
            }
        }

        // Value was null — target ran but produced no result
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Helm chart versions data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Helm chart versions target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        // Boolean is not a meaningful type for helm version data
        if (typeof point.value === 'boolean') {
            return {
                status: 'gather_failure',
                status_reason: 'Helm releases data is a boolean, expected version string.',
                raw_output: point.raw_output,
            }
        }

        const value: string | number = point.value

        return {
            status: 'healthy',
            status_reason: 'Helm chart versions for all releases have been collected successfully.',
            display_value: value,
            raw_output: point.raw_output,
        }
    }
}

export default HelmChartVersionsChecker
