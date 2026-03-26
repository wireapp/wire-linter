/**
 * Checks disk usage on the Cassandra data directory.
 *
 * Consumes the databases/cassandra/data_disk_usage target. The value might
 * be a number (percentage), a string (percentage text), or a boolean
 * (pass/fail from the collector). Cassandra data usually lives on its own
 * mount, so it can fill up independently of the root filesystem.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class DataDiskUsageChecker extends BaseChecker {
    readonly path: string = 'cassandra/data_disk_usage'
    readonly name: string = 'Data directory disk usage'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Monitors disk usage on the Cassandra data directory mount. When disk fills past **85%**, Cassandra compaction stalls and writes begin failing, which blocks message delivery and user operations in Wire.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/cassandra/data_disk_usage')

        // Data wasn't collected for some reason
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra data directory disk usage data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `df -h` runs successfully on the target host\n3. Verify the Cassandra data directory path is correct in the gatherer config\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Couldn\'t get disk usage data for the data directory.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra data disk usage data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Data disk usage target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // Collector gave us a pass/fail result
        if (typeof val === 'boolean') {
            if (val) {
                return {
                    status: 'healthy',
                    status_reason: 'Cassandra data directory **passed** the disk usage check.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'Cassandra data directory **failed** the disk usage check (boolean false from collector).',
                fix_hint: '1. Check current disk usage: `df -h /var/lib/cassandra/data`\n2. Identify large SSTables: `du -sh /var/lib/cassandra/data/*/`\n3. Run compaction to reclaim space: `nodetool compact`\n4. Check for snapshot buildup: `nodetool listsnapshots` and clear old ones with `nodetool clearsnapshot`\n5. If disk is critically full, consider adding storage or moving data to a larger volume',
                recommendation: 'Cassandra data directory failed the disk usage check.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Try to get a number out of whatever we got
        const usage: number = typeof val === 'number' ? val : parseFloat(String(val))

        // Can't parse it, so we don't know the actual state
        if (isNaN(usage)) {
            return {
                status: 'warning',
                status_reason: 'Received unparseable disk usage value **{{raw_value}}** from Cassandra, cannot determine actual usage.',
                fix_hint: '1. Manually check disk usage on the Cassandra data directory: `df -h /var/lib/cassandra/data`\n2. Verify the gatherer target is collecting the correct metric\n3. Review the raw collector output for formatting issues',
                recommendation: `Got unexpected disk usage value from Cassandra: «${val}». Can't determine actual usage.`,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { raw_value: val },
            }
        }

        // Over 85% is bad news for data directories
        if (usage > 85) {
            return {
                status: 'unhealthy',
                status_reason: 'Cassandra data directory is at **{{usage}}%** usage, exceeding the **85%** critical threshold.',
                fix_hint: '1. Check disk usage breakdown: `df -h /var/lib/cassandra/data`\n2. Identify large SSTables: `du -sh /var/lib/cassandra/data/*/`\n3. Clear old snapshots: `nodetool listsnapshots` then `nodetool clearsnapshot -t <snapshot_name>`\n4. Run compaction to reclaim space: `nodetool compact`\n5. If still full, consider adding storage capacity or cleaning up tombstoned data with `nodetool garbagecollect`',
                recommendation: `Data directory is at ${usage}% full. This needs attention now, otherwise Cassandra will start having issues.`,
                display_value: usage,
                display_unit: '%',
                raw_output: point.raw_output,
                template_data: { usage },
            }
        }

        // Getting full, should start thinking about capacity
        if (usage > 70) {
            return {
                status: 'warning',
                status_reason: 'Cassandra data directory is at **{{usage}}%** usage, exceeding the **70%** warning threshold but below the **85%** critical threshold.',
                fix_hint: '1. Monitor disk growth trend: `df -h /var/lib/cassandra/data`\n2. Clear old snapshots if any: `nodetool listsnapshots` then `nodetool clearsnapshot -t <snapshot_name>`\n3. Plan for additional storage before usage reaches the **85%** critical threshold\n4. Consider running `nodetool compact` during a maintenance window to reclaim space',
                recommendation: `Data directory is at ${usage}%. Time to plan for more storage before it becomes critical.`,
                display_value: usage,
                display_unit: '%',
                raw_output: point.raw_output,
                template_data: { usage },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Cassandra data directory is at **{{usage}}%** usage, well within healthy limits.',
            display_value: usage,
            display_unit: '%',
            raw_output: point.raw_output,
            template_data: { usage },
        }
    }
}

export default DataDiskUsageChecker
