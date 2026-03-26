/**
 * Checks memory usage across all VMs.
 *
 * Grabs vm/<node>/memory_used and vm/<node>/memory_total to figure out
 * percentage usage per VM. If total is missing for a VM, just report raw used.
 * Verdict comes from the worst offender.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

interface VmMemoryEntry {
    name: string
    used: number
    total: number | undefined
    percentage: number | undefined
}

export class VmMemoryUsageChecker extends BaseChecker {
    readonly path: string = 'vm/memory_usage'
    readonly name: string = 'Memory usage'
    readonly category: string = 'VMs'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors **memory usage** across all VMs and reports the worst case. When a VM runs out of memory, the kernel **OOM-killer** terminates processes unpredictably, taking down Wire services.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const used_points = data.find(/^vm\/[^/]+\/memory_used$/)
        const total_points = data.find(/^vm\/[^/]+\/memory_total$/)

        // Nothing to work with
        if (used_points.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'VM memory usage data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to all VMs and can read `/proc/meminfo` or run `free -m`. Verify that VM hostnames in the inventory match the actual hosts.',
                recommendation: 'Memory usage data not collected.',
            }
        }

        // Build a lookup so we don't loop total_points for every VM
        const total_by_vm = new Map<string, number>()
        for (const point of total_points) {
            const vm_name = point.path.split('/')[1] ?? 'unknown'
            const parsed = parse_number(point)
            // Skip unparseable total values (e.g. malformed strings)
            if (parsed !== null) {
                total_by_vm.set(vm_name, parsed)
            }
        }

        // Turn each used datapoint into a full entry with percentage if we have total
        const vm_entries: VmMemoryEntry[] = used_points.reduce<VmMemoryEntry[]>((acc, point) => {
            const vm_name = point.path.split('/')[1] ?? 'unknown'
            const used = parse_number(point)
            // Skip VMs with unparseable used values
            if (used === null) return acc
            const total = total_by_vm.get(vm_name)

            // Only compute percentage if we have a total and it's not zero
            const percentage = total !== undefined && total > 0
                ? (used / total) * 100
                : undefined

            acc.push({ name: vm_name, used, total, percentage })
            return acc
        }, [])

        // Filter to entries with percentages and sort by worst first
        const with_pct = vm_entries
            .filter((entry): entry is VmMemoryEntry & { percentage: number } => entry.percentage !== undefined)
            .sort((a, b) => b.percentage - a.percentage)

        // Build the full output string for all VMs
        const combined_raw: string = vm_entries
            .map((entry) => {
                if (entry.total !== undefined && entry.percentage !== undefined) {
                    return `${entry.name}: ${entry.used}Gi / ${entry.total}Gi (${entry.percentage.toFixed(1)}%)`
                }
                return `${entry.name}: ${entry.used}Gi used (total unknown)`
            })
            .join('\n')

        // Check the worst percentage and pick a verdict
        if (with_pct.length > 0) {
            const worst = with_pct[0]!
            const pct_display = worst.percentage.toFixed(1)

            if (worst.percentage > 90) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Worst VM memory usage is **{{pct_display}}%** on **{{vm_name}}**, exceeding the **90%** critical threshold.',
                    fix_hint: '1. SSH into **{{vm_name}}** and identify memory-hungry processes:\n   ```\n   ps aux --sort=-%mem | head -20\n   ```\n2. Check container memory usage: `crictl stats`\n3. Review pod memory limits: `kubectl top pods --all-namespaces --sort-by=memory`\n4. Look for memory leaks in application pods: `kubectl describe pod <pod-name> -n wire`\n5. If usage remains high, **add more RAM** to the VM or **reduce workloads**.',
                    recommendation: `${worst.name} memory at ${pct_display}%. Risk of OOM. Reduce workloads or add RAM.`,
                    display_value: `worst: ${pct_display}% (${worst.name})`,
                    raw_output: combined_raw,
                    template_data: { pct_display, vm_name: worst.name },
                }
            }

            if (worst.percentage > 80) {
                return {
                    status: 'warning',
                    status_reason: 'Worst VM memory usage is **{{pct_display}}%** on **{{vm_name}}**, approaching the **90%** critical threshold.',
                    fix_hint: '1. SSH into **{{vm_name}}** and review memory consumers:\n   ```\n   ps aux --sort=-%mem | head -20\n   ```\n2. Check container stats: `crictl stats`\n3. Review pod memory requests/limits: `kubectl top pods --all-namespaces --sort-by=memory`\n4. Plan for **memory expansion** before usage reaches **90%** to avoid OOM kills.',
                    recommendation: `${worst.name} memory at ${pct_display}%. Monitor for OOM conditions.`,
                    display_value: `worst: ${pct_display}% (${worst.name})`,
                    raw_output: combined_raw,
                    template_data: { pct_display, vm_name: worst.name },
                }
            }

            return {
                status: 'healthy',
                status_reason: 'Worst VM memory usage is **{{pct_display}}%** on **{{vm_name}}**, well within safe limits.',
                display_value: `worst: ${pct_display}% (${worst.name})`,
                raw_output: combined_raw,
                template_data: { pct_display, vm_name: worst.name },
            }
        }

        // All used values were unparseable — nothing to report
        if (vm_entries.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'VM memory usage data could not be parsed (all values are non-numeric).',
                recommendation: 'Memory usage data could not be read. Check that the memory_used targets are returning numeric values.',
            }
        }

        // Can't compute percentages, so just show the highest raw used value
        const highest_used = [...vm_entries].sort((a, b) => b.used - a.used)[0]!

        return {
            status: 'warning',
            status_reason: `Highest VM memory consumption is ${highest_used.used}Gi on ${highest_used.name} (total RAM unknown, cannot compute percentage).`,
            recommendation: 'Total RAM data was not collected for any VM. Ensure memory_total targets run successfully so memory pressure can be properly assessed.',
            display_value: `${highest_used.name}: ${highest_used.used}Gi used`,
            raw_output: combined_raw,
            template_data: { used: highest_used.used, vm_name: highest_used.name },
        }
    }
}

export default VmMemoryUsageChecker
