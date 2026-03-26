/**
 * Checks whether the Cassandra replication factor matches the actual node count.
 *
 * Consumes TWO targets: config/cassandra_replication_factor (boolean, true
 * means RF matches nodes) and optionally databases/cassandra/node_count (number)
 * for display purposes. When the replication factor exceeds the node count,
 * all schema migrations crash.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class CassandraReplicationChecker extends BaseChecker {
    readonly path: string = 'helm_config/cassandra_replication'
    readonly name: string = 'Cassandra replication factor vs actual node count'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Validates that the Cassandra **replication factor** matches the actual number of cluster nodes. When the replication factor exceeds the node count, all **schema migrations fail**.'

    check(data: DataLookup): CheckResult {
        const config_point = data.get('config/cassandra_replication_factor')
        const node_count_point = data.get('databases/cassandra/node_count')

        // Primary target data was not collected
        if (!config_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra replication vs node count data was not collected.',
                fix_hint: '1. Verify the gatherer has access to Cassandra cluster info:\n   ```\n   kubectl get configmap -n wire | grep cassandra\n   ```\n2. Re-run the gatherer ensuring the `config/cassandra_replication_factor` target succeeds.',
                recommendation: 'Couldn\'t get Cassandra replication vs node count data.',
            }
        }

        // Aggregate raw output from both consumed data points
        const combined_raw: string = [config_point?.raw_output, node_count_point?.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        const val = config_point.value

        // Node count for display purposes, parsed safely to handle string values from gatherer
        const node_count: number | undefined = node_count_point ? parse_number(node_count_point) ?? undefined : undefined

        // All four RF probe methods failed data is inconclusive. Render as a
        // warning rather than healthy (which would mask misconfigured clusters)
        // or unhealthy (which would be a false alarm).
        if (val === 'inconclusive') {
            const health_info: string = (config_point.metadata as Record<string, string>)?.health_info ?? ''
            return {
                status: 'warning',
                status_reason: 'Replication factor check was **inconclusive** — all probe methods failed.',
                fix_hint: '1. Check CQL access to the Cassandra cluster:\n   ```\n   kubectl exec -n wire -it cassandra-0 -- cqlsh -e "DESCRIBE KEYSPACES"\n   ```\n2. Verify ConfigMap availability:\n   ```\n   helm get values wire-server -n wire | grep replicationFactor\n   ```\n3. Re-run the gatherer after fixing access.',
                recommendation: health_info || 'Could not determine Cassandra replication factor - all probe methods failed. Check CQL access and ConfigMap availability.',
                display_value: 'inconclusive',
                raw_output: combined_raw,
            }
        }

        // Gatherer emits null when data collection failed (e.g. CQL unreachable).
        // Treat as gather_failure rather than falling through to the unhealthy branch.
        if (val === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra replication vs node count data was not collected.',
                recommendation: 'Couldn\'t get Cassandra replication vs node count data.',
                raw_output: combined_raw,
            }
        }

        const bool_val: boolean = val as boolean

        // Build display value including node count if available
        const display: string | boolean = node_count !== undefined
            ? `RF matches: ${bool_val}, nodes: ${node_count}`
            : bool_val

        // Boolean true means replication factor matches node count
        if (bool_val === true) {
            return {
                status: 'healthy',
                status_reason: node_count !== undefined
                    ? 'Cassandra replication factor matches the **{{node_count}}** available node(s).'
                    : 'Cassandra replication factor matches the available node(s).',
                display_value: display,
                raw_output: combined_raw,
                template_data: { node_count },
            }
        }

        // Boolean false, RF doesn't match node count
        return {
            status: 'unhealthy',
            status_reason: node_count !== undefined
                ? 'Cassandra replication factor does **not match** the **{{node_count}}** available node(s).'
                : 'Cassandra replication factor does **not match** the available node(s).',
            fix_hint: '1. Check the current replication factor in your helm values:\n   ```\n   helm get values wire-server -n wire | grep replicationFactor\n   ```\n2. Verify the actual Cassandra node count:\n   ```\n   kubectl exec -n wire -it cassandra-0 -- nodetool status\n   ```\n3. Set the replication factor to match the node count in your values file and apply:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: 'Cassandra replication factor doesn\'t match node count. When RF exceeds nodes, schema migrations fail.',
            display_value: display,
            raw_output: combined_raw,
            template_data: { node_count },
        }
    }
}

export default CassandraReplicationChecker
