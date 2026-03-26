/**
 * Watches for Helm releases stuck in a bad state.
 *
 * The helm/release_status target returns a boolean or string indicating
 * release health. Stuck releases block future upgrades and need manual
 * fixing. We're checking that nothing is caught in pending-install,
 * pending-upgrade, or failed states.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class HelmReleaseStatusChecker extends BaseChecker {
    readonly path: string = 'upgrades/helm_release_status'
    readonly name: string = 'Helm release status not stuck'
    readonly category: string = 'Upgrades / Migrations'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Checks for Helm releases stuck in `pending-install`, `pending-upgrade`, or `failed` state. Stuck releases **block all future upgrades** and need manual intervention to resolve.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('helm/release_status') ?? data.get('direct/helm/release_status')

        // We couldn't gather the target data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `helm/release_status` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can run Helm commands: `helm list -n wire`\n2. Check that the Helm binary is installed and the kubeconfig is accessible\n3. Review the gatherer logs for permission errors or timeouts',
                recommendation: 'Helm release status not stuck data not collected.',
            }
        }

        // A null value means the gatherer ran but couldn't produce a result (e.g. helm unreachable)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Helm release status data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Helm release status target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean

        // If it's a string, a non-empty value contains the names of stuck releases
        // (e.g. "wire-server: pending-upgrade"), which means unhealthy. An empty
        // string means no stuck releases were found, which is healthy.
        if (typeof val === 'string') {
            const has_stuck_state = /pending-install|pending-upgrade|pending-rollback|failed|superseded|uninstalling/i.test(val)

            if (val.length > 0 && !has_stuck_state) {
                return {
                    status: 'unhealthy',
                    status_reason: 'One or more Helm releases are stuck in a non-deployed state.',
                    recommendation: 'Helm releases stuck in pending-install, pending-upgrade, or failed state. This blocks all future upgrades.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            return {
                status: 'healthy',
                status_reason: 'All Helm releases are in deployed state.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { detail: val || 'no details available' },
            }
        }

        // True means no releases are stuck
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All Helm releases are in **deployed** state.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // False means releases are stuck
        return {
            status: 'unhealthy',
            status_reason: 'One or more Helm releases are **stuck** in a non-deployed state.',
            fix_hint: '1. Identify stuck releases:\n   ```\n   helm list -n wire --all | grep -vE "deployed"\n   ```\n2. For a release in `failed` state, check the history:\n   ```\n   helm history <release-name> -n wire\n   ```\n3. Roll back to the last successful revision:\n   ```\n   helm rollback <release-name> <last-good-revision> -n wire\n   ```\n4. For `pending-install` / `pending-upgrade`, the release lock may be stuck. Force cleanup:\n   ```\n   kubectl delete secret -n wire -l owner=helm,status=pending-install\n   kubectl delete secret -n wire -l owner=helm,status=pending-upgrade\n   ```\n5. Retry the upgrade after clearing the stuck state',
            recommendation: 'Helm releases stuck in pending-install, pending-upgrade, or failed state. This blocks all future upgrades.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default HelmReleaseStatusChecker
