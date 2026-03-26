/**
 * Checks Team Settings service health.
 *
 * This is where admins manage their Wire teams. If it's down,
 * they can't configure anything.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class TeamSettingsChecker extends BaseChecker {
    readonly path: string = 'wire_services/team_settings'
    readonly name: string = 'Team Settings, healthy'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Team Settings** web application is running. If it is down, team administrators cannot manage users, permissions, or team configuration.'

    check(data: DataLookup): CheckResult {
        const point = data.get('wire_services/team_settings/healthy')

        // Didn't collect data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Team Settings health data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `team_settings` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Team Settings health check',
                recommendation: 'Team Settings, healthy data not collected.',
            }
        }

        // Collection failed (null value means the gatherer couldn't reach the service)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Team Settings health check data was collected but the value is null.',
                recommendation: 'Team Settings health data could not be determined.',
                raw_output: point.raw_output,
            }
        }

        const is_healthy = coerce_boolean(point.value)

        // Service is down
        if (is_healthy === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Team Settings service is not responding to health checks.',
                recommendation: 'Team Settings is down.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Service is up
        if (is_healthy === true) {
            return {
                status: 'healthy',
                status_reason: 'Team Settings service is healthy.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `Team Settings health data has an unexpected value: ${String(point.value)}`,
            recommendation: 'Team Settings, healthy returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default TeamSettingsChecker
