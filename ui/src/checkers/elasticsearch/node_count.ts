/**
 * Makes sure you've got enough Elasticsearch nodes. Less than 3 and you can't
 * properly distribute replicas, which kills your fault tolerance for search and indexing.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class NodeCountChecker extends BaseChecker {
    readonly path: string = 'elasticsearch/node_count'
    readonly name: string = 'Node count'
    readonly category: string = 'Data / Elasticsearch'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Verifies the Elasticsearch cluster has enough nodes to distribute replicas for fault tolerance. Fewer than **3 nodes** means Wire search indexing has no redundancy, and a single node failure can take search offline.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/elasticsearch/node_count')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch node count data was not collected.',
                fix_hint: '1. Verify connectivity to the Elasticsearch cluster\n2. Check that the node API is reachable: `curl -s http://localhost:9200/_cat/nodes?v`\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Node count data not collected.',
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch node count value could not be parsed as a number.',
                recommendation: 'The collected node count data was not in a recognizable numeric format.',
                raw_output: point.raw_output,
            }
        }

        if (count === 0) {
            return {
                status: 'unhealthy',
                status_reason: 'Found **0** Elasticsearch nodes; the cluster is completely non-functional.',
                fix_hint: '1. Check if Elasticsearch is running on each host: `systemctl status elasticsearch`\n2. Review Elasticsearch logs: `journalctl -u elasticsearch`\n3. Verify cluster configuration in `/etc/elasticsearch/elasticsearch.yml`\n4. Check that network settings allow node discovery: verify `discovery.seed_hosts` and `cluster.initial_master_nodes`\n5. Start Elasticsearch if it is stopped: `sudo systemctl start elasticsearch`',
                recommendation: 'No Elasticsearch nodes are running - the cluster is completely non-functional.',
                display_value: count,
                display_unit: 'nodes',
                raw_output: point.raw_output,
            }
        }

        if (count < 3) {
            return {
                status: 'warning',
                status_reason: 'Found **{{node_count}}** Elasticsearch node(s), which is below the recommended **3** for proper replica distribution.',
                fix_hint: '1. Check current node status: `curl -s http://localhost:9200/_cat/nodes?v`\n2. Verify all expected nodes are running: `systemctl status elasticsearch` on each host\n3. Add more nodes to the cluster by installing Elasticsearch on additional hosts and configuring them with the same `cluster.name`\n4. After adding nodes, check shard allocation: `curl -s http://localhost:9200/_cat/allocation?v`',
                recommendation: 'Consider adding more Elasticsearch nodes for redundancy.',
                display_value: count,
                display_unit: 'nodes',
                raw_output: point.raw_output,
                template_data: { node_count: count },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Found **{{node_count}}** Elasticsearch nodes, meeting the recommended minimum of **3** for replica distribution.',
            display_value: count,
            display_unit: 'nodes',
            raw_output: point.raw_output,
            template_data: { node_count: count },
        }
    }
}

export default NodeCountChecker
