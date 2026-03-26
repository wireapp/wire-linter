/**
 * Checks Webapp service health.
 *
 * The webapp serves the Wire client UI. If it's down,
 * users can't access Wire.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class WebappChecker extends BaseChecker {
    readonly path: string = 'wire_services/webapp'
    readonly name: string = 'Webapp, healthy'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Webapp** service (Wire web client) is running. If it is down, users cannot access Wire through their browser.'

    check(data: DataLookup): CheckResult {
        const point = data.get('wire_services/webapp/healthy')

        // Didn't collect data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Webapp health data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `webapp` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Webapp health check',
                recommendation: 'Webapp, healthy data not collected.',
            }
        }

        // Collection failed (null value means the gatherer couldn't reach the service)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Webapp health check data was collected but the value is null.',
                recommendation: 'Webapp health data could not be determined.',
                raw_output: point.raw_output,
            }
        }

        const is_healthy = coerce_boolean(point.value)

        // Service is down
        if (is_healthy === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Webapp service is not responding to health checks.',
                recommendation: 'Webapp is down.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Service is up
        if (is_healthy === true) {
            return {
                status: 'healthy',
                status_reason: 'Webapp service is healthy.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `Webapp health data has an unexpected value: ${String(point.value)}`,
            recommendation: 'Webapp, healthy returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default WebappChecker
