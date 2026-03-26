/**
 * Checks memory usage on the admin host machine.
 *
 * Uses the host/memory_usage target (percentage of RAM in use).
 * Warns if over 75%, flags as unhealthy if over 90%.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class MemoryUsageChecker extends BaseChecker {
    readonly path: string = 'host_admin/memory_usage'
    readonly name: string = 'Memory usage'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors **RAM usage** on the admin host. High memory consumption leads to **OOM kills**, which can terminate critical Wire backend processes without warning.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const point = data.get('host/memory_usage')

        // Can't check without the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Memory usage data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can read `/proc/meminfo` or run `free -m`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t get memory usage data.',
            }
        }

        const usage = parse_number(point)

        // Value could not be parsed as a number (e.g. empty string, garbage)
        if (usage === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Memory usage value could not be parsed as a number.',
                recommendation: `The memory usage target returned "${point.value}" which is not a valid numeric value. Check the target command output.`,
                raw_output: point.raw_output,
            }
        }

        // Running critically low on memory
        if (usage > 90) {
            return {
                status: 'unhealthy',
                status_reason: 'Memory usage is at **{{usage}}%**, which exceeds the **90%** critical threshold.',
                fix_hint: '1. Identify memory-hungry processes: `ps aux --sort=-%mem | head -20`\n2. Check for memory leaks in containers: `crictl stats`\n3. Clear page cache if safe: `sync && echo 3 > /proc/sys/vm/drop_caches`\n4. If usage remains high, **add more RAM** or **reduce workloads** on this host.',
                recommendation: 'Memory is almost full. You might want to add more RAM or trim some workloads.',
                display_value: usage,
                display_unit: '%',
                raw_output: point.raw_output,
                template_data: { usage },
            }
        }

        // Starting to worry about memory
        if (usage > 75) {
            return {
                status: 'warning',
                status_reason: 'Memory usage is at **{{usage}}%**, approaching the **90%** critical threshold.',
                fix_hint: '1. Review memory consumers: `ps aux --sort=-%mem | head -20`\n2. Check container resource limits: `crictl stats`\n3. Plan for **memory expansion** before usage reaches **90%** to avoid OOM kills.',
                recommendation: 'Memory usage is getting high. Keep an eye on it and maybe think about adding capacity.',
                display_value: usage,
                display_unit: '%',
                raw_output: point.raw_output,
                template_data: { usage },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Memory usage is at **{{usage}}%**, well within safe limits.',
            display_value: usage,
            display_unit: '%',
            raw_output: point.raw_output,
            template_data: { usage },
        }
    }
}

export default MemoryUsageChecker
