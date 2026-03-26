/**
 * Reports the uptime of the admin host machine.
 *
 * Uses the host/uptime target. Just showing you how long the machine
 * has been running always healthy, nothing to worry about here.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class UptimeChecker extends BaseChecker {
    readonly path: string = 'host_admin/uptime'
    readonly name: string = 'Uptime'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Reports how long the admin host has been running since last reboot. A **recent reboot** may indicate instability, while very long uptimes may mean the system is missing **kernel security patches**.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const point = data.get('host/uptime')

        // Didn't manage to get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Uptime data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can run `uptime`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t get uptime data.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Uptime data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Uptime target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const uptime: string = String(point.value)

        return {
            status: 'healthy',
            status_reason: 'Admin host has been up for **{{uptime}}**.',
            display_value: uptime,
            raw_output: point.raw_output,
            template_data: { uptime },
        }
    }
}

export default UptimeChecker
