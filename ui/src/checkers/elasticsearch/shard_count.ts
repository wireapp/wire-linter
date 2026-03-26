/**
 * Pulls the total shard count from Elasticsearch and displays it back.
 *
 * Uses the «databases/elasticsearch/shard_count» target which is just a number.
 * Nothing here can actually fail your cluster it's informational only and always comes back healthy.
 * The shard count just gives you useful context to have around when you're digging into cluster issues.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class ShardCountChecker extends BaseChecker {
    readonly path: string = 'elasticsearch/shard_count'
    readonly name: string = 'Shard count'
    readonly category: string = 'Data / Elasticsearch'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Reports the total Elasticsearch shard count for operational context. While not a pass/fail check, an unusually high shard count can indicate **over-sharding**, which degrades cluster performance and Wire search responsiveness.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/elasticsearch/shard_count')

        // If we didn't get the shard count back from the target, just say so
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch shard count data was not collected.',
                fix_hint: '1. Verify connectivity to the Elasticsearch cluster\n2. Check that the shard API is reachable: `curl -s http://localhost:9200/_cat/shards?v`\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Shard count data not collected.',
            }
        }

        const count = parse_number(point)

        // Value couldn't be parsed as a number (null, string mismatch, or gatherer error)
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch shard count value could not be parsed as a number.',
                recommendation: point.metadata?.error ?? 'The gathered shard count data was not in a recognized numeric format.',
                raw_output: point.raw_output,
            }
        }

        // Just report the number back there's no health check here, it's always fine
        return {
            status: 'healthy',
            status_reason: 'Elasticsearch cluster has **{{shard_count}}** shard(s). This is an informational check with no health threshold.',
            display_value: count,
            display_unit: 'shards',
            raw_output: point.raw_output,
            template_data: { shard_count: count },
        }
    }
}

export default ShardCountChecker
