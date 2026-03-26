/**
 * Checks SFTd (conference calling) service health.
 *
 * SFTd handles Selective Forwarding for group calls. If it's down,
 * conference calling doesn't work.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class SftdChecker extends BaseChecker {
    readonly path: string = 'wire_services/sftd'
    readonly name: string = 'SFTd (conference calling), healthy'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **SFTd** service (Selective Forwarding Turn for group calls) is running. If SFTd is down, group and conference calls will not work.'

    check(data: DataLookup): CheckResult {
        // Skip when calling or SFT is not enabled
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled in the deployment configuration.' }
        }
        if (data.config && !data.config.options.expect_sft) {
            return { status: 'not_applicable', status_reason: 'SFT (conference calling) is not enabled.' }
        }

        const point = data.get('wire_services/sftd/healthy')

        // Didn't get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'SFTd health data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `sftd` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the SFTd health check',
                recommendation: 'SFTd (conference calling), healthy data not collected.',
            }
        }

        // Collection failed (null value means the gatherer couldn't reach the service)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'SFTd health check data was collected but the value is null.',
                recommendation: 'SFTd health data could not be determined.',
                raw_output: point.raw_output,
            }
        }

        const is_healthy = coerce_boolean(point.value)

        // Service is down
        if (is_healthy === false) {
            return {
                status: 'unhealthy',
                status_reason: 'SFTd conference calling service is not responding to health checks.',
                recommendation: 'SFTd (conference calling) is down.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Service is up
        if (is_healthy === true) {
            return {
                status: 'healthy',
                status_reason: 'SFTd conference calling service is running and healthy.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `SFTd health data has an unexpected value: ${String(point.value)}`,
            recommendation: 'SFTd (conference calling), healthy returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default SftdChecker
