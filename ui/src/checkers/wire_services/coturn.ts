/**
 * Checks Coturn (TURN server) service health.
 *
 * Consumes ONE target: wire_services/coturn/healthy (boolean).
 * Coturn relays media traffic for clients behind restrictive NATs.
 * If it goes down, some users won't be able to make calls.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class CoturnChecker extends BaseChecker {
    readonly path: string = 'wire_services/coturn'
    readonly name: string = 'Coturn (TURN server), healthy'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Coturn** TURN relay server is running. Coturn relays media traffic for clients behind restrictive NATs or firewalls -- if it is down, those users cannot make or receive calls.'

    check(data: DataLookup): CheckResult {
        // Skip when calling is not enabled
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled in the deployment configuration.' }
        }

        const point = data.get('wire_services/coturn/healthy')

        // Couldn't collect Coturn health data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Coturn health data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `coturn` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Coturn health check',
                recommendation: 'Coturn (TURN server), healthy data not collected.',
            }
        }

        // Collection failed (null value means the gatherer couldn't reach the service)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Coturn health check data was collected but the value is null.',
                recommendation: 'Coturn health data could not be determined.',
                raw_output: point.raw_output,
            }
        }

        const is_healthy = coerce_boolean(point.value)

        // Coturn is down
        if (is_healthy === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Coturn TURN server is not responding to health checks.',
                recommendation: 'Coturn (TURN server) is down.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Coturn is up
        if (is_healthy === true) {
            return {
                status: 'healthy',
                status_reason: 'Coturn TURN server is running and healthy.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `Coturn health data has an unexpected value: ${String(point.value)}`,
            recommendation: 'Coturn (TURN server), healthy returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default CoturnChecker
