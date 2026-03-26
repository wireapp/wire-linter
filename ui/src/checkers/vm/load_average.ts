/**
 * Checks 1-minute load average across all VMs and reports the worst one.
 *
 * When CPU count data is available for a VM, load is normalized per-CPU so
 * thresholds scale with machine size. Falls back to absolute thresholds
 * when cpu_count data is missing.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

interface VmLoadEntry {
    name: string
    load: number
    cpus: number | null
    // Normalized load per CPU, or raw load when cpu_count is unavailable
    effective_load: number
}

export class VmLoadAverageChecker extends BaseChecker {
    readonly path: string = 'vm/load_average'
    readonly name: string = 'Load average'
    readonly category: string = 'VMs'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors the 1-minute load average across all VMs, normalized by CPU count when available. Load above the CPU count means processes are queuing for CPU time, causing Wire services to respond slowly or time out.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const points = data.find(/^vm\/[^/]+\/load_average$/)

        // Nothing collected yet
        if (points.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'VM load average data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to all VMs and can read `/proc/loadavg`. Verify that VM hostnames in the inventory match the actual hosts.',
                recommendation: 'Load average data not collected.',
            }
        }

        // Build entries with per-VM CPU count when available. parse_number()
        // safely converts string values like "3.14" that the gatherer may emit.
        const vm_entries: VmLoadEntry[] = points
            .map((point) => {
                const host_name: string = point.path.split('/')[1] ?? 'unknown'
                const load: number | null = parse_number(point)

                // Look up cpu_count for this specific VM
                const cpu_point = data.get(`vm/${host_name}/cpu_count`)
                const cpus: number | null = cpu_point ? parse_number(cpu_point) : null

                if (load === null) {
                    return null
                }

                // Normalize by CPU count when available, otherwise use raw load
                const effective_load: number = cpus !== null && cpus > 0
                    ? load / cpus
                    : load

                return { name: host_name, load, cpus, effective_load }
            })
            // Drop any points where load could not be parsed as a number
            .filter((entry): entry is VmLoadEntry => entry !== null)
            // Sort by effective load so the worst offender is first
            .sort((a, b) => b.effective_load - a.effective_load)

        // All load values were unparseable
        if (vm_entries.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'VM load average values could not be parsed as numbers.',
                recommendation: 'The load average targets returned values that are not valid numbers. Check the target command output.',
            }
        }

        // Worst effective load wins the verdict
        const worst = vm_entries[0]!

        // Show all VMs with CPU context so you can see the whole picture
        const combined_raw: string = vm_entries
            .map((entry) => {
                const cpu_info: string = entry.cpus !== null
                    ? ` (${entry.cpus} CPUs, ${entry.effective_load.toFixed(2)} per CPU)`
                    : ' (CPU count unknown)'
                return `${entry.name}: ${entry.load}${cpu_info}`
            })
            .join('\n')

        // When CPU count is known, use per-CPU thresholds (matching host_admin/load_average)
        if (worst.cpus !== null && worst.cpus > 0) {
            return this.check_normalized(worst, combined_raw)
        }

        // Fall back to absolute thresholds when CPU count is unavailable
        return this.check_absolute(worst, combined_raw)
    }

    /** Evaluate using per-CPU normalized thresholds. */
    private check_normalized(worst: VmLoadEntry, combined_raw: string): CheckResult {
        const cpus = worst.cpus!
        const cpu_label: string = `${cpus} CPU core${cpus === 1 ? '' : 's'}`

        // Load exceeds available CPUs — processes are queuing
        if (worst.load > cpus) {
            return {
                status: 'unhealthy',
                status_reason: `Worst VM load average is ${worst.load} on ${worst.name}, which exceeds the available ${cpu_label}.`,
                recommendation: `${worst.name} load at ${worst.load} but only has ${cpus} CPUs. Investigate CPU-intensive processes.`,
                display_value: `worst: ${worst.load} (${worst.name}, ${cpu_label})`,
                raw_output: combined_raw,
            }
        }

        // Above 70% of CPU capacity — getting close to saturation
        if (worst.load > cpus * 0.7) {
            return {
                status: 'warning',
                status_reason: `Worst VM load average is ${worst.load} on ${worst.name}, above 70% of the available ${cpu_label}.`,
                recommendation: `${worst.name} load elevated at ${worst.load} relative to ${cpus} CPUs.`,
                display_value: `worst: ${worst.load} (${worst.name}, ${cpu_label})`,
                raw_output: combined_raw,
            }
        }

        return {
            status: 'healthy',
            status_reason: `Worst VM load average is ${worst.load} on ${worst.name}, well within the capacity of ${cpu_label}.`,
            display_value: `worst: ${worst.load} (${worst.name}, ${cpu_label})`,
            raw_output: combined_raw,
        }
    }

    /** Evaluate using absolute thresholds when CPU count is unavailable. */
    private check_absolute(worst: VmLoadEntry, combined_raw: string): CheckResult {
        // Above 8 is bad news
        if (worst.load > 8) {
            return {
                status: 'unhealthy',
                status_reason: `Worst VM load average is ${worst.load} on ${worst.name}, exceeding the critical threshold of 8 (CPU count unavailable for normalization).`,
                recommendation: `${worst.name} load at ${worst.load}. Investigate CPU-intensive processes.`,
                display_value: `worst: ${worst.load} (${worst.name})`,
                raw_output: combined_raw,
                template_data: { load: worst.load, vm_name: worst.name },
            }
        }

        // Above 4 is getting concerning
        if (worst.load > 4) {
            return {
                status: 'warning',
                status_reason: `Worst VM load average is ${worst.load} on ${worst.name}, above the warning threshold of 4 (CPU count unavailable for normalization).`,
                recommendation: `${worst.name} load elevated at ${worst.load}.`,
                display_value: `worst: ${worst.load} (${worst.name})`,
                raw_output: combined_raw,
                template_data: { load: worst.load, vm_name: worst.name },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Worst VM load average is **{{load}}** on **{{vm_name}}**, well within normal range.',
            display_value: `worst: ${worst.load} (${worst.name})`,
            raw_output: combined_raw,
            template_data: { load: worst.load, vm_name: worst.name },
        }
    }
}

export default VmLoadAverageChecker
