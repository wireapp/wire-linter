/**
 * Port connectivity matrix for Wire deployments.
 *
 * Every port that must be reachable between kubenodes and datanodes for Wire
 * to work on-premise. This is the single source of truth for both the
 * connectivity checker and the Ports view UI.
 *
 * Use get_expected_ports() to look up ports for a source/target role pair.
 */

// Ours
import type { PortCategory, PortDefinition } from './port_types'

/** Port connectivity grouped by source to target direction. */
export const PORT_MATRIX: PortCategory[] = [
    {
        source_type: 'kubenode',
        target_type: 'datanode',
        label:       'Kubenode \u2192 Datanode',
        ports: [
            { port: 9042,  protocol: 'tcp', service: 'Cassandra CQL' },
            { port: 7000,  protocol: 'tcp', service: 'Cassandra gossip' },
            { port: 9200,  protocol: 'tcp', service: 'OpenSearch REST' },
            { port: 9300,  protocol: 'tcp', service: 'OpenSearch transport' },
            { port: 5432,  protocol: 'tcp', service: 'PostgreSQL' },
            { port: 9000,  protocol: 'tcp', service: 'MinIO S3' },
            { port: 5672,  protocol: 'tcp', service: 'RabbitMQ AMQP' },
            { port: 15672, protocol: 'tcp', service: 'RabbitMQ management' },
        ],
    },
    {
        source_type: 'kubenode',
        target_type: 'kubenode',
        label:       'Kubenode \u2192 Kubenode',
        ports: [
            { port: 6443,  protocol: 'tcp', service: 'Kubernetes API' },
            { port: 2379,  protocol: 'tcp', service: 'etcd client' },
            { port: 2380,  protocol: 'tcp', service: 'etcd peer' },
            { port: 10250, protocol: 'tcp', service: 'Kubelet API' },
        ],
    },
    {
        source_type: 'datanode',
        target_type: 'datanode',
        label:       'Datanode \u2192 Datanode',
        ports: [
            { port: 7000, protocol: 'tcp', service: 'Cassandra gossip' },
            { port: 9300, protocol: 'tcp', service: 'OpenSearch transport' },
            { port: 9000, protocol: 'tcp', service: 'MinIO replication' },
        ],
    },
]

/**
 * Look up expected ports for a source to target role pair.
 *
 * Returns the matching PortDefinition array, or an empty array if no matrix
 * entry exists for that direction (e.g. datanode to kubenode has no
 * defined requirements).
 *
 * @param source_type Role of the host initiating the connection
 * @param target_type Role of the host receiving the connection
 * @returns Array of expected port definitions for this direction
 */
export function get_expected_ports(
    source_type: PortCategory['source_type'],
    target_type: PortCategory['target_type'],
): PortDefinition[] {
    // Linear scan is fine matrix has only a few categories
    const category = PORT_MATRIX.find(
        (cat) => cat.source_type === source_type && cat.target_type === target_type,
    )

    // No matrix entry means no expected connectivity for this pair
    return category?.ports ?? []
}
