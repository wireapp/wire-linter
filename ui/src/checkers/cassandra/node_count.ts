/**
 * Checks the number of Cassandra nodes in the cluster.
 *
 * Consumes the databases/cassandra/node_count target (number).
 * Wire uses RF3, so you need at least 3 nodes. That's the baseline
 * for keeping data safe across replication.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class NodeCountChecker extends BaseChecker {
    readonly path: string = 'cassandra/node_count'
    readonly name: string = 'Node count'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Ensures the Cassandra cluster has at least **3 nodes** to support replication factor 3. Fewer nodes mean Wire cannot safely replicate user data, conversations, and message metadata across the cluster.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/cassandra/node_count')

        // Couldn't get the node count data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra node count data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `nodetool status` runs successfully on the target host\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: "Couldn't collect node count data.",
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra node count value could not be parsed as a number.',
                recommendation: 'The collected node count data was not in a recognizable numeric format.',
                raw_output: point.raw_output,
            }
        }

        // Less than 3 nodes won't work with RF3
        if (count < 3) {
            return {
                status: 'unhealthy',
                status_reason: 'Found **{{node_count}}** Cassandra node(s), which is below the minimum **3** required for replication factor 3.',
                fix_hint: '1. Check current cluster membership: `nodetool status`\n2. Verify all expected nodes are running: `systemctl status cassandra` on each host\n3. Add nodes to reach at least 3 for RF3: bootstrap new nodes with `cassandra-env.sh` configured to join the cluster\n4. After adding nodes, run `nodetool cleanup` on existing nodes to redistribute data',
                recommendation: 'You need at least 3 nodes to run replication factor 3.',
                display_value: count,
                display_unit: 'nodes',
                raw_output: point.raw_output,
                template_data: { node_count: count },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Found **{{node_count}}** Cassandra nodes, meeting the minimum **3** required for replication factor 3.',
            display_value: count,
            display_unit: 'nodes',
            raw_output: point.raw_output,
            template_data: { node_count: count },
        }
    }
}

export default NodeCountChecker
