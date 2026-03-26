/**
 * Checks whether your Elasticsearch cluster is healthy (green), degraded (yellow),
 * or in trouble (red). Red is bad-primary shards are unassigned and you could lose data.
 * Yellow is a warning-replicas aren't allocated, so you've lost redundancy but things
 * still work. Green means everything's good.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClusterHealthChecker extends BaseChecker {
    readonly path: string = 'elasticsearch/cluster_health'
    readonly name: string = 'Cluster health'
    readonly category: string = 'Data / Elasticsearch'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Evaluates the Elasticsearch cluster health status (**green**/**yellow**/**red**). A red cluster has unassigned primary shards risking data loss, while yellow means lost redundancy -- both degrade or break Wire search functionality.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/elasticsearch/cluster_health')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch cluster health data was not collected.',
                fix_hint: '1. Verify connectivity to the Elasticsearch cluster\n2. Check that the cluster API is reachable: `curl -s http://localhost:9200/_cluster/health`\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Cluster health data not collected.',
            }
        }

        const val: string = String(point.value).toLowerCase()

        if (val === 'red') {
            return {
                status: 'unhealthy',
                status_reason: 'Elasticsearch cluster health is **red**, meaning primary shards are unassigned and data loss may occur.',
                fix_hint: '1. Check cluster health details: `curl -s http://localhost:9200/_cluster/health?pretty`\n2. List unassigned shards: `curl -s http://localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason | grep UNASSIGNED`\n3. Check allocation explanation: `curl -s -X GET http://localhost:9200/_cluster/allocation/explain?pretty`\n4. Review node status: `curl -s http://localhost:9200/_cat/nodes?v`\n5. Check Elasticsearch logs on each node: `journalctl -u elasticsearch`\n6. If nodes are down, restart them and wait for shard recovery',
                recommendation: 'Elasticsearch cluster is RED. Data loss may occur. Investigate immediately.',
                display_value: point.value ?? undefined,
                raw_output: point.raw_output,
            }
        }

        if (val === 'yellow') {
            return {
                status: 'warning',
                status_reason: 'Elasticsearch cluster health is **yellow**, meaning some replica shards are not allocated and redundancy is reduced.',
                fix_hint: '1. Check cluster health details: `curl -s http://localhost:9200/_cluster/health?pretty`\n2. List unassigned replicas: `curl -s http://localhost:9200/_cat/shards?v&h=index,shard,prirep,state | grep UNASSIGNED`\n3. Check allocation explanation: `curl -s -X GET http://localhost:9200/_cluster/allocation/explain?pretty`\n4. Common causes: insufficient nodes for replica count, disk watermark reached, or node recently restarted\n5. Check disk usage: `curl -s http://localhost:9200/_cat/allocation?v`',
                recommendation: 'Elasticsearch cluster is YELLOW. Some replicas not allocated. Check node capacity.',
                display_value: point.value ?? undefined,
                raw_output: point.raw_output,
            }
        }

        if (val === 'green') {
            return {
                status: 'healthy',
                status_reason: 'Elasticsearch cluster health is GREEN, all primary and replica shards are allocated.',
                display_value: point.value ?? undefined,
                raw_output: point.raw_output,
            }
        }

        // Unrecognized status — don't silently report healthy
        return {
            status: 'warning',
            status_reason: `Elasticsearch cluster reported unrecognized health status «${val}». This may indicate a problem or an unsupported Elasticsearch version.`,
            recommendation: `Elasticsearch cluster health status «${val}» is not a recognized value (expected green/yellow/red). Investigate the cluster status manually.`,
            display_value: point.value ?? undefined,
            raw_output: point.raw_output,
            template_data: { health_status: val },
        }
    }
}

export default ClusterHealthChecker
