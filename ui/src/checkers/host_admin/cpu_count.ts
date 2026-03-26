/**
 * Reports the CPU core count on the admin host machine.
 *
 * Consumes the host/cpu_count target. Just informational stuff,
 * always healthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class CpuCountChecker extends BaseChecker {
    readonly path: string = 'host_admin/cpu_count'
    readonly name: string = 'CPU count'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports the number of **CPU cores** on the admin host. Useful for gauging whether the machine has enough processing power to run Wire backend services without bottlenecks.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const point = data.get('host/cpu_count')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'CPU count data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can run `nproc`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t get CPU count data.',
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number (e.g. null, empty string)
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'CPU count value could not be parsed.',
                recommendation: 'Check that the host/cpu_count target is collecting data correctly.',
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Admin host has **{{count}}** CPU core{{count_suffix}}.',
            display_value: count,
            display_unit: 'cores',
            raw_output: point.raw_output,
            template_data: { count, count_suffix: count === 1 ? '' : 's' },
        }
    }
}

export default CpuCountChecker
