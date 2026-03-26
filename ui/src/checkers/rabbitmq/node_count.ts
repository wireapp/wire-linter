/**
 * Checks the number of RabbitMQ nodes in the cluster.
 *
 * Consumes the databases/rabbitmq/node_count target. You need at least 3 nodes
 * for high availability. Fewer than 3 is a problem.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class NodeCountChecker extends BaseChecker {
    readonly path: string = 'rabbitmq/node_count'
    readonly name: string = 'Node count'
    readonly category: string = 'Data / RabbitMQ'
    readonly interest = 'Health, Setup' as const
    readonly explanation: string = 'Confirms the RabbitMQ cluster has at least **3 nodes** for high availability. Fewer nodes mean a single failure can take down the message broker and disrupt all Wire backend communication.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('databases/rabbitmq/node_count') ?? data.get('direct/rabbitmq/node_count')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ node count data was not collected.',
                fix_hint: '1. Verify connectivity to the RabbitMQ node\n2. Check that `rabbitmqctl cluster_status` runs successfully\n3. If using the management API: `curl -u guest:guest http://<host>:15672/api/nodes`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Node count data not collected.',
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ node count value could not be parsed as a number.',
                recommendation: 'The collected node count data was not in a recognizable numeric format.',
                raw_output: point.raw_output,
            }
        }

        // Can't do HA with fewer than 3 nodes
        if (count < 3) {
            return {
                status: 'warning',
                status_reason: 'RabbitMQ cluster has only **{{count}}** node(s), below the recommended minimum of **3** for high availability.',
                fix_hint: '1. Check current nodes: `rabbitmqctl cluster_status`\n2. Add a new RabbitMQ node to the cluster: `rabbitmqctl join_cluster rabbit@<existing_node>`\n3. Verify the new node joined: `rabbitmqctl cluster_status` should show all nodes\n4. Enable queue mirroring for HA: `rabbitmqctl set_policy ha-all ".*" \'{"ha-mode":"all"}\'`',
                recommendation: 'RabbitMQ cluster should have 3 nodes for high availability.',
                display_value: count,
                raw_output: point.raw_output,
                template_data: { count },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'RabbitMQ cluster has **{{count}}** nodes, meeting the high-availability requirement of **3+**.',
            display_value: count,
            raw_output: point.raw_output,
            template_data: { count },
        }
    }
}

export default NodeCountChecker
