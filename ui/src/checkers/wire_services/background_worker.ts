/**
 * Checks Background Worker service health.
 *
 * Consumes ONE target: wire_services/background_worker/healthy (boolean).
 * Simple up/down check. The worker needs to be running for async tasks
 * like notifications and cleanup jobs to work.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class BackgroundWorkerChecker extends BaseChecker {
    readonly path: string = 'wire_services/background_worker'
    readonly name: string = 'Background Worker, healthy'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Background Worker** service is running. It handles asynchronous tasks like team deletions, notifications, and cleanup jobs -- if it is down, these operations silently stop processing.'

    check(data: DataLookup): CheckResult {
        const point = data.get('wire_services/background_worker/healthy')

        // Target data wasn't collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Background Worker health data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `background_worker` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Background Worker health check',
                recommendation: 'Background Worker, healthy data not collected.',
            }
        }

        // Collection failed (null value means the gatherer couldn't reach the service)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Background Worker health check data was collected but the value is null.',
                recommendation: 'Background Worker health data could not be determined.',
                raw_output: point.raw_output,
            }
        }

        const is_healthy = coerce_boolean(point.value)

        // Service is down
        if (is_healthy === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Background Worker service is not responding to health checks.',
                recommendation: 'Background Worker is down.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Service is up
        if (is_healthy === true) {
            return {
                status: 'healthy',
                status_reason: 'Background Worker service is running and healthy.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `Background Worker health data has an unexpected value: ${String(point.value)}`,
            recommendation: 'Background Worker, healthy returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default BackgroundWorkerChecker
