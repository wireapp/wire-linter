/**
 * Checks the number of PostgreSQL nodes in the repmgr cluster.
 *
 * Consumes the databases/postgresql/node_count target. PostgreSQL HA
 * needs at least 3 nodes (1 primary + 2 standbys) for automatic failover.
 * Fewer than 3 is a problem.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class NodeCountChecker extends BaseChecker {
    readonly path: string = 'postgresql/node_count'
    readonly name: string = 'Node count (primary + standbys)'
    readonly category: string = 'Data / PostgreSQL'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Ensures the PostgreSQL repmgr cluster has at least **3 nodes** (1 primary + 2 standbys) for automatic failover. With fewer nodes, a primary failure requires manual intervention and causes Wire service downtime.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/postgresql/node_count')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL node count data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the PostgreSQL nodes\n2. Check that `pg_isready` responds: `pg_isready -h <host>`\n3. Verify repmgr is configured: `repmgr cluster show`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Node count (primary + standbys) data not collected.',
            }
        }

        const count = parse_number(point)

        // Value couldn't be parsed as a number (gatherer may emit a string or null)
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL node count value could not be parsed as a number.',
                recommendation: 'The gathered node count data was not in a recognized numeric format.',
                raw_output: point.raw_output,
            }
        }

        // 0 nodes means either PostgreSQL is completely down or repmgr isn't configured
        // (e.g. single-node setup with no HA). Either way the HA layer is absent unhealthy.
        if (count === 0) {
            return {
                status: 'unhealthy',
                status_reason: 'Found **0** PostgreSQL nodes registered in repmgr; the HA cluster is completely absent.',
                fix_hint: '1. Check if PostgreSQL is running: `pg_isready` or `systemctl status postgresql`\n2. Check if repmgr is configured: `repmgr cluster show`\n3. If repmgr is not installed, follow the Wire deployment guide to set up PostgreSQL HA\n4. If the cluster was previously running, check logs: `journalctl -u postgresql`\n5. Verify repmgr daemon: `systemctl status repmgrd`',
                recommendation: 'No PostgreSQL nodes are registered in repmgr. Either the cluster is down or repmgr is not configured. HA is completely absent.',
                display_value: count,
                raw_output: point.raw_output,
            }
        }

        // 1-2 nodes: cluster is partially running but can't do automatic failover
        if (count < 3) {
            return {
                status: 'warning',
                status_reason: 'Found **{{node_count}}** PostgreSQL node(s), which is below the recommended **3** (1 primary + 2 standbys) for automatic failover.',
                fix_hint: '1. Check current cluster membership: `repmgr cluster show` or `patronictl list`\n2. Verify all expected nodes are running: `pg_isready -h <host>` on each\n3. Add standby nodes to reach 3: `repmgr standby clone -h <primary_host> -d repmgr` then `repmgr standby register`\n4. After adding nodes, verify replication: `psql -c "SELECT client_addr, state FROM pg_stat_replication"` on the primary',
                recommendation: 'PostgreSQL HA requires 3 nodes (1 primary + 2 standbys) for automatic failover.',
                display_value: count,
                raw_output: point.raw_output,
                template_data: { node_count: count },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Found **{{node_count}}** PostgreSQL nodes, meeting the recommended **3** for automatic failover.',
            display_value: count,
            raw_output: point.raw_output,
            template_data: { node_count: count },
        }
    }
}

export default NodeCountChecker
