/**
 * Checks if Account Pages service is healthy.
 *
 * Reads wire_services/account_pages/healthy (boolean).
 * Account Pages handles user-facing account management like password resets and email verification.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class AccountPagesChecker extends BaseChecker {
    readonly path: string = 'wire_services/account_pages'
    readonly name: string = 'Account Pages, healthy'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Account Pages** service is running. It handles user-facing account management like password resets and email verification -- if it is down, users cannot complete these self-service flows.'

    check(data: DataLookup): CheckResult {
        const point = data.get('wire_services/account_pages/healthy')

        // No data collected for this service
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Account Pages health data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `account_pages` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Account Pages health check',
                recommendation: 'Account Pages, healthy data not collected.',
            }
        }

        // Collection failed (null value means the gatherer couldn't reach the service)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Account Pages health check data was collected but the value is null.',
                recommendation: 'Account Pages health data could not be determined.',
                raw_output: point.raw_output,
            }
        }

        const is_healthy = coerce_boolean(point.value)

        // Service is not responding
        if (is_healthy === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Account Pages service is not responding to health checks.',
                recommendation: 'Account Pages is down.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Service is up
        if (is_healthy === true) {
            return {
                status: 'healthy',
                status_reason: 'Account Pages service is running and healthy.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `Account Pages health data has an unexpected value: ${String(point.value)}`,
            recommendation: 'Account Pages, healthy returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default AccountPagesChecker
