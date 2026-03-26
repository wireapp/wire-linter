/**
 * Checks the 1-minute load average on the admin host machine.
 *
 * Uses the load_average and cpu_count targets together. When load gets
 * higher than the CPU count, the system is overloaded.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class LoadAverageChecker extends BaseChecker {
    readonly path: string = 'host_admin/load_average'
    readonly name: string = 'Load average'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors the **1-minute load average** relative to CPU count on the admin host. When load exceeds available cores, processes queue up and Wire services become slow or **unresponsive**.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const load_point = data.get('host/load_average')
        const cpu_point = data.get('host/cpu_count')

        // Can't proceed without both data points
        if (!load_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Load average data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can read `/proc/loadavg`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t get load average data.',
            }
        }

        if (!cpu_point) {
            return {
                status: 'gather_failure',
                status_reason: 'CPU count data was not collected, cannot evaluate load relative to available cores.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can run `nproc`. The load average was collected (**{{load}}**) but without the CPU count, the check cannot determine if load is excessive.',
                recommendation: 'Couldn\'t get CPU count.',
                display_value: load_point.value as number,
                raw_output: load_point.raw_output,
                template_data: { load: load_point.value as number },
            }
        }

        const load: number | null = parse_number(load_point)
        const cpus: number | null = parse_number(cpu_point)

        // If either value can't be parsed as a number, we can't evaluate
        if (load === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Load average value could not be parsed as a number.',
                recommendation: 'The load average target returned a value that is not a valid number. Check the target command output.',
            }
        }

        if (cpus === null) {
            return {
                status: 'gather_failure',
                status_reason: 'CPU count value could not be parsed as a number.',
                recommendation: 'The CPU count target returned a value that is not a valid number. Check the target command output.',
                display_value: load,
                raw_output: load_point.raw_output,
            }
        }

        // Combine both data points for the raw output
        const combined_raw: string = [load_point.raw_output, cpu_point.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        // When load is higher than CPU count, things are backed up
        if (load > cpus) {
            return {
                status: 'unhealthy',
                status_reason: 'Load average is **{{load}}**, which exceeds the available **{{cpus}}** CPU core{{cpus_suffix}}.',
                fix_hint: '1. Identify CPU-intensive processes: `top -bn1 | head -20`\n2. Check for runaway containers: `crictl stats`\n3. Look for stuck processes: `ps aux --sort=-%cpu | head -20`\n4. If load is sustained, consider **adding more CPU cores** or **redistributing workloads** across nodes.',
                recommendation: `Load is at ${load} but you only have ${cpus} CPUs. Check what's eating CPU.`,
                display_value: load,
                raw_output: combined_raw,
                template_data: { load, cpus, cpus_suffix: cpus === 1 ? '' : 's' },
            }
        }

        // Getting close to maxing out
        if (load > cpus * 0.7) {
            return {
                status: 'warning',
                status_reason: 'Load average is **{{load}}**, above **70%** of the available **{{cpus}}** CPU core{{cpus_suffix}}.',
                fix_hint: '1. Monitor CPU-intensive processes: `top -bn1 | head -20`\n2. Check container resource usage: `crictl stats`\n3. Consider **scaling horizontally** or **adding CPU cores** before load exceeds capacity.',
                recommendation: 'Load is getting high relative to available CPUs.',
                display_value: load,
                raw_output: combined_raw,
                template_data: { load, cpus, cpus_suffix: cpus === 1 ? '' : 's' },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Load average is **{{load}}**, well within the capacity of **{{cpus}}** CPU core{{cpus_suffix}}.',
            display_value: load,
            raw_output: combined_raw,
            template_data: { load, cpus, cpus_suffix: cpus === 1 ? '' : 's' },
        }
    }
}

export default LoadAverageChecker
