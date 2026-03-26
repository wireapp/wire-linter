/**
 * Reports the worst disk usage across all VMs. If any VM is
 * running low on space, you can have problems. Logs fill up,
 * container images pile on, data grows, and suddenly a service
 * just stops. So we check all the disk targets and report back
 * the one that's in the worst shape.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class VmDiskUsageChecker extends BaseChecker {
    readonly path: string = 'vm/disk_usage'
    readonly name: string = 'Disk usage'
    readonly category: string = 'VMs'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors **disk usage** across all VMs and reports the worst case. Full disks prevent log writes, block container image pulls, and cause **database corruption** or service crashes.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const points = data.find(/^vm\/[^/]+\/disk_usage$/)

        // If we didn't get any disk data, that's a problem
        if (points.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'VM disk usage data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to all VMs and can run `df -h`. Verify that VM hostnames in the inventory match the actual hosts.',
                recommendation: 'Disk usage data not collected.',
            }
        }

        // Extract name and usage from each data point, parsing the value
        // safely (the gatherer may emit "92%" as a string). Skip any
        // points where the value is not a valid number.
        const vm_entries: { name: string; usage: number }[] = points
            .map((point) => ({
                name: point.path.split('/')[1] ?? 'unknown',
                usage: parse_number(point),
            }))
            .filter((entry): entry is { name: string; usage: number } => entry.usage !== null)
            .sort((a, b) => b.usage - a.usage)

        // All values were unparseable — none survived the filter
        if (vm_entries.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'VM disk usage values could not be parsed as numbers.',
                recommendation: 'The disk usage targets returned values that are not valid numbers. Check the target command output.',
            }
        }

        // First one is the worst since we sorted
        const worst = vm_entries[0]!

        // Show all VMs in the raw output so the user can see the full picture
        const combined_raw: string = vm_entries
            .map((entry) => `${entry.name}: ${entry.usage}%`)
            .join('\n')

        // 85% and above is critical. The VM is almost full
        if (worst.usage > 85) {
            return {
                status: 'unhealthy',
                status_reason: 'Worst VM disk usage is **{{usage}}%** on **{{vm_name}}**, exceeding the **85%** critical threshold.',
                fix_hint: '1. SSH into **{{vm_name}}** and identify large directories:\n   ```\n   du -sh /* | sort -rh | head -20\n   ```\n2. Clean up old logs: `journalctl --vacuum-size=500M`\n3. Remove unused container images: `crictl rmi --prune`\n4. Check for large core dumps: `find / -name "core.*" -size +100M`\n5. If cleanup is insufficient, **expand the VM disk** or add additional storage.',
                recommendation: `${worst.name} disk at ${worst.usage}%. Expand storage or clean up immediately.`,
                display_value: `worst: ${worst.usage}% (${worst.name})`,
                raw_output: combined_raw,
                template_data: { usage: worst.usage, vm_name: worst.name },
            }
        }

        // 70% starts getting tight. Not emergency yet, but think about cleanup
        if (worst.usage > 70) {
            return {
                status: 'warning',
                status_reason: 'Worst VM disk usage is **{{usage}}%** on **{{vm_name}}**, approaching the **85%** critical threshold.',
                fix_hint: '1. SSH into **{{vm_name}}** and review disk usage:\n   ```\n   du -sh /* | sort -rh | head -20\n   ```\n2. Clean old journal logs: `journalctl --vacuum-size=500M`\n3. Remove unused container images: `crictl rmi --prune`\n4. Plan for **disk expansion** before usage reaches **85%**.',
                recommendation: `${worst.name} disk at ${worst.usage}%. Plan for storage expansion.`,
                display_value: `worst: ${worst.usage}% (${worst.name})`,
                raw_output: combined_raw,
                template_data: { usage: worst.usage, vm_name: worst.name },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Worst VM disk usage is **{{usage}}%** on **{{vm_name}}**, well within safe limits.',
            display_value: `worst: ${worst.usage}% (${worst.name})`,
            raw_output: combined_raw,
            template_data: { usage: worst.usage, vm_name: worst.name },
        }
    }
}

export default VmDiskUsageChecker
