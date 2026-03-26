/**
 * Checks disk usage on the admin host machine.
 *
 * Consumes the host/disk_usage target (percentage of root filesystem used).
 * Warns above 70%, gets unhealthy above 85%.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class DiskUsageChecker extends BaseChecker {
    readonly path: string = 'host_admin/disk_usage'
    readonly name: string = 'Disk usage'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors **disk usage** on the admin host. When disks fill up, services cannot write logs or data, databases stop functioning, and the system may become **unresponsive**.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const point = data.get('host/disk_usage')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Disk usage data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can run `df -h`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t get disk usage data.',
            }
        }

        // Data was collected but contained no usable value
        if (point.value === null || point.value === undefined) {
            return {
                status: 'gather_failure',
                status_reason: 'Disk usage data was collected but contained no value.',
                recommendation: 'The disk usage target ran but returned no numeric result. Check whether the target command succeeded.',
                raw_output: point.raw_output,
            }
        }

        const usage = parse_number(point)

        // Value could not be parsed as a number (e.g. empty string, garbage)
        if (usage === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Disk usage value could not be parsed as a number.',
                recommendation: `The disk usage target returned "${point.value}" which is not a valid numeric value. Check the target command output.`,
                raw_output: point.raw_output,
            }
        }

        // Above 85% is bad
        if (usage > 85) {
            return {
                status: 'unhealthy',
                status_reason: 'Disk usage is at **{{usage}}%**, which exceeds the **85%** critical threshold.',
                fix_hint: '1. Check which directories are using the most space:\n   ```\n   du -sh /* | sort -rh | head -20\n   ```\n2. Clean up old logs: `journalctl --vacuum-size=500M`\n3. Remove unused container images: `crictl rmi --prune`\n4. If cleanup is insufficient, **expand the volume** or add additional storage.',
                recommendation: 'Disk is almost full on the admin host. Add more storage or clean stuff up, now.',
                display_value: usage,
                display_unit: '%',
                raw_output: point.raw_output,
                template_data: { usage },
            }
        }

        // Above 70% getting risky
        if (usage > 70) {
            return {
                status: 'warning',
                status_reason: 'Disk usage is at **{{usage}}%**, approaching the **85%** critical threshold.',
                fix_hint: '1. Identify large directories: `du -sh /* | sort -rh | head -20`\n2. Clean old journal logs: `journalctl --vacuum-size=500M`\n3. Remove unused container images: `crictl rmi --prune`\n4. Plan for **storage expansion** before usage reaches **85%**.',
                recommendation: 'Disk is getting full on the admin host. Think about adding more storage soon.',
                display_value: usage,
                display_unit: '%',
                raw_output: point.raw_output,
                template_data: { usage },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Disk usage is at **{{usage}}%**, well within safe limits.',
            display_value: usage,
            display_unit: '%',
            raw_output: point.raw_output,
            template_data: { usage },
        }
    }
}

export default DiskUsageChecker
