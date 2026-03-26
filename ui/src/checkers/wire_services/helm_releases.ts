/**
 * Checks that all Helm releases are in deployed state.
 *
 * If a release is stuck or failed, it's left your services in a weird state.
 * This looks at helm/release_status to catch that.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class HelmReleasesChecker extends BaseChecker {
    readonly path: string = 'wire_services/helm_releases'
    readonly name: string = 'Helm releases, all deployed'
    readonly category: string = 'Wire Services'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies all **Helm releases** are in `deployed` state. A stuck or failed Helm release means a service upgrade did not complete, leaving the deployment in an inconsistent state that can cause outages.'

    check(data: DataLookup): CheckResult {
        const point = data.get('helm/release_status')

        // Didn't get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Helm release status data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Helm targets enabled\n2. Check that `helm` is available on the target host\n3. Review the gatherer logs for errors during the Helm release status check',
                recommendation: 'Helm releases, all deployed data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Helm release status data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Helm release status target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const value: boolean | string | number = point.value

        // Got a boolean back
        if (typeof value === 'boolean') {
            if (!value) {
                return {
                    status: 'unhealthy',
                    status_reason: 'One or more Helm releases are **not** in `deployed` state.',
                    fix_hint: '1. List all releases: `helm list -A`\n2. Identify releases not in `deployed` state\n3. For failed releases, check history: `helm history <release-name> -n wire`\n4. Roll back if needed: `helm rollback <release-name> <revision> -n wire`\n5. For pending releases, wait or delete and re-install: `helm delete <release-name> -n wire`',
                    recommendation: 'Some Helm releases are not in deployed state. Check <command>helm list -A</command> for stuck/failed releases.',
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'All Helm releases are in `deployed` state.',
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // Got a string back check if it looks bad
        if (typeof value === 'string') {
            const lower: string = value.toLowerCase()

            // Looks like something failed or is still pending
            if (lower.includes('failed') || lower.includes('pending')) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Helm release status contains problematic state: **{{helm_status}}**.',
                    fix_hint: '1. List all releases: `helm list -A`\n2. Identify the problematic release(s) from the status output\n3. Check release history: `helm history <release-name> -n wire`\n4. For failed releases, roll back: `helm rollback <release-name> <revision> -n wire`\n5. For pending releases, check if an operation is still running or if it needs manual cleanup',
                    recommendation: 'Some Helm releases are not in deployed state. Check <command>helm list -A</command> for stuck/failed releases.',
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { helm_status: value },
                }
            }

            // Says everything's deployed
            if (lower.includes('deployed')) {
                return {
                    status: 'healthy',
                    status_reason: 'All Helm releases are in `deployed` state: **{{helm_status}}**.',
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { helm_status: value },
                }
            }
        }

        // Couldn't figure out what this means
        return {
            status: 'gather_failure',
            status_reason: 'Helm release status value could not be interpreted: **{{helm_status}}**.',
            fix_hint: '1. Run `helm list -A` manually and check the output format\n2. Verify the gatherer is parsing the Helm output correctly\n3. Check the raw output above for unexpected data formats',
            recommendation: 'Helm release status could not be determined from the collected data.',
            display_value: value,
            raw_output: point.raw_output,
            template_data: { helm_status: value },
        }
    }
}

export default HelmReleasesChecker
