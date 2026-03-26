/**
 * Checks whether NTP is synchronized on all Cassandra/data nodes.
 *
 * Consumes the databases/cassandra/ntp_synchronized target (boolean).
 * Time drift on data nodes is critical: Cassandra uses timestamps for
 * conflict resolution, and even small drift causes quorum write failures
 * and data inconsistency.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class NtpSynchronizedChecker extends BaseChecker {
    readonly path: string = 'cassandra/ntp_synchronized'
    readonly name: string = 'NTP synchronized (all data nodes)'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Confirms **NTP** clock synchronization across all Cassandra nodes. Cassandra uses timestamps for conflict resolution, so even small clock drift causes quorum write failures and data inconsistency in Wire.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/cassandra/ntp_synchronized')

        // No data collected for this check
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'NTP synchronization data was not collected from Cassandra nodes.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `timedatectl` or `ntpstat` runs successfully on each node\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'NTP synchronized (all data nodes) data not collected.',
            }
        }

        const is_synchronized = coerce_boolean(point.value)

        // Clocks out of sync = Cassandra breaks, quorum writes fail
        if (is_synchronized === false) {
            return {
                status: 'unhealthy',
                status_reason: 'NTP is **not synchronized** on one or more Cassandra nodes, which causes time drift and breaks quorum writes.',
                fix_hint: '1. Check NTP status on each node: `timedatectl status`\n2. If NTP is inactive, enable it: `sudo timedatectl set-ntp true`\n3. Verify chrony or ntpd is running: `systemctl status chronyd` or `systemctl status ntpd`\n4. Check clock offset: `chronyc tracking` or `ntpq -p`\n5. If offset is large, force a sync: `sudo chronyc makestep` or `sudo ntpdate -b <ntp_server>`\n6. Verify sync across all nodes: compare `date -u` output on each Cassandra host',
                recommendation: 'NTP is not synchronized on Cassandra nodes. This is a problem: time drift breaks quorum writes. Get NTP fixed.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // Synchronized or unrecognised value (treat as healthy — gatherer returned data)
        if (is_synchronized === true) {
            return {
                status: 'healthy',
                status_reason: 'NTP is synchronized across all Cassandra nodes.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `NTP synchronization data has an unexpected value: ${String(point.value)}`,
            recommendation: 'NTP synchronized (all data nodes) returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default NtpSynchronizedChecker
