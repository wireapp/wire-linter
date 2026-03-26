/**
 * Checks PostgreSQL replication status across the cluster.
 *
 * Consumes the databases/postgresql/replication_status target (a string).
 * If it's not «healthy», replication's broken and failover won't work.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ReplicationStatusChecker extends BaseChecker {
    readonly path: string = 'postgresql/replication_status'
    readonly name: string = 'Replication status'
    readonly category: string = 'Data / PostgreSQL'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Checks whether PostgreSQL **streaming replication** is healthy across the cluster. Broken replication means standbys fall behind the primary, so automatic failover will not work and data loss is likely if the primary goes down.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/postgresql/replication_status')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL replication status data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the PostgreSQL nodes\n2. Check that `pg_isready` responds on the primary: `pg_isready -h <primary_host>`\n3. Verify repmgr is installed and configured: `repmgr cluster show`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Replication status data not collected.',
            }
        }

        // Gatherer returned a data point but couldn't read the actual value
        if (point.value === null || point.value === undefined) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL replication status was collected but the value is missing — the gatherer likely could not connect to PostgreSQL.',
                recommendation: 'Check that PostgreSQL is reachable and that the gatherer has the correct credentials.',
                raw_output: point.raw_output,
            }
        }

        const val: string = point.value as string

        // If it's not «healthy», something's wrong
        if (val !== 'healthy') {
            return {
                status: 'unhealthy',
                status_reason: 'PostgreSQL replication status is **{{replication_status}}** instead of **healthy**, indicating replication is broken and failover will not work.',
                fix_hint: '1. Check repmgr cluster status: `repmgr cluster show`\n2. Verify replication connections on the primary: `psql -c "SELECT client_addr, state, sent_lsn, replay_lsn FROM pg_stat_replication"`\n3. Check standby recovery status: `psql -c "SELECT pg_is_in_recovery(), pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()"`\n4. Review PostgreSQL logs on primary and standbys: `journalctl -u postgresql`\n5. If replication is broken, try rejoining the standby: `repmgr standby clone --force -h <primary_host> -d repmgr`\n6. After fixing, verify with `patronictl list` or `repmgr cluster show`',
                recommendation: 'PostgreSQL replication is not healthy. Check repmgr cluster show for details.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { replication_status: val },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'PostgreSQL streaming replication is **healthy** across the cluster.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default ReplicationStatusChecker
