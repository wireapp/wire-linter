/**
 * Shows the current Wire-server version as informational data.
 *
 * The helm/releases target provides version information. We always
 * return healthy here because checking currency would require knowing
 * the latest release, which we don't have. The version is displayed
 * as the main data point.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class VersionCurrencyChecker extends BaseChecker {
    readonly path: string = 'upgrades/version_currency'
    readonly name: string = 'Wire-server version currency'
    readonly category: string = 'Upgrades / Migrations'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports the currently deployed **wire-server** Helm chart version. Displayed as an informational data point so operators can verify they are running the expected release.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('helm/releases') ?? data.get('direct/helm/releases')

        // We couldn't gather the target data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `helm/releases` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can run Helm commands: `helm list -n wire`\n2. Check that the Helm binary is installed and the kubeconfig is accessible\n3. Review the gatherer logs for permission errors or timeouts',
                recommendation: 'Wire-server version currency data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Helm releases data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Helm releases target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // Just extract the version string for display
        const display: string = typeof val === 'string' ? val : String(val)

        return {
            status: 'healthy',
            status_reason: 'Wire-server is running version **{{version}}**.',
            display_value: display,
            raw_output: point.raw_output,
            template_data: { version: display },
        }
    }
}

export default VersionCurrencyChecker
