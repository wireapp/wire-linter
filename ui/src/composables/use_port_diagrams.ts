/**
 * use_port_diagrams.ts Diagram computation pipeline for port connectivity results.
 *
 * Pulled out from PortsTab.vue. This composable is the complete self-contained
 * pipeline for the diagram view mode:
 *   port_results → unique_nodes → per-port worst status → rendered SVGs
 *
 * The two helper functions (worst_status_per_port, status_priority) are pure
 * utilities exported individually so they can be reused if diagram logic gets more complex.
 */

// External
import { computed } from 'vue'
import type { Ref } from 'vue'

// Ours
import type { PortCheckResult, NodeInfo } from '../lib/port_types'
import { render_kubenode_svg } from '../lib/kubenode_svg'
import { render_datanode_svg } from '../lib/datanode_svg'
import { render_external_svg } from '../lib/external_svg'
import { sanitize_svg } from '../lib/svg_helpers'

// -- Pure helpers --

/** Known name prefixes for external nodes (load balancers, monitoring agents, clients, etc.). */
const EXTERNAL_PREFIXES = ['lb-', 'load-balancer-', 'monitor-', 'external-', 'client-']

/** Known name prefixes for datanode hosts, used as fallback when the gatherer doesn't provide node type. */
const DATANODE_PREFIXES = ['datanode-', 'data-node-', 'db-', 'cassandra-', 'elasticsearch-', 'es-', 'minio-', 'redis-', 'rabbitmq-', 'rmq-', 'postgres-', 'pg-', 'mongo-']

/**
 * Infer node type from hostname and connectivity patterns when the gatherer hasn't provided an explicit type.
 *
 * Classification order:
 *   1. EXTERNAL_PREFIXES match → 'external' (fast path for well-known external name patterns)
 *   2. DATANODE_PREFIXES match → 'datanode'
 *   3. Node never appears as a source in port_results → 'external'
 *      The gatherer runs from inside the cluster, so every internal node initiates at least
 *      one connectivity test (appears as a source). External entities like load balancers are
 *      only ever targets — they never appear as sources.
 *   4. Default → 'kubenode'
 *
 * @param name          Hostname to classify.
 * @param port_results  Full set of port results used for connectivity pattern analysis.
 * @returns             The inferred node type.
 */
export function infer_node_type(name: string, port_results: PortCheckResult[]): 'kubenode' | 'datanode' | 'external' {
    for (const prefix of EXTERNAL_PREFIXES) {
        if (name.startsWith(prefix)) return 'external'
    }
    for (const prefix of DATANODE_PREFIXES) {
        if (name.startsWith(prefix)) return 'datanode'
    }

    // Connectivity pattern analysis: nodes that never initiate connections are external.
    // Skip when there are no results — every node would look "external" if the list is empty.
    if (port_results.length > 0 && !port_results.some(r => r.source_name === name)) {
        return 'external'
    }

    return 'kubenode'
}

/**
 * Priority for worst-status logic: higher means worse.
 * «open» gets 1, so it beats unrecognized stuff (0) but loses to error, filtered, or closed.
 */
export function status_priority(status: string): number {
    if (status === 'closed') return 4
    if (status === 'filtered') return 3
    if (status === 'error') return 2
    if (status === 'open') return 1
    return 0
}

/** Takes a list of results and builds a worst-status-per-port map. */
export function worst_status_per_port(results: PortCheckResult[]): Map<number, string> {
    const map = new Map<number, string>()
    for (const r of results) {
        const existing = map.get(r.port)
        if (!existing || status_priority(r.status) > status_priority(existing)) {
            map.set(r.port, r.status)
        }
    }
    return map
}

// -- Composable --

/**
 * Composable that derives all diagram state from a reactive list of port results.
 *
 * Takes in the full list of port check results and spits out computed refs for the nodes
 * and their SVG diagrams.
 */
export function use_port_diagrams(port_results: Ref<PortCheckResult[]>) {
    /** Pull out all unique nodes from port results, both sources and targets. */
    const unique_nodes = computed((): NodeInfo[] => {
        // Pass 1: scan all results to collect explicit node types.
        // This ensures an explicit type provided anywhere in the result set wins over
        // an inferred type, regardless of which result first introduced the node name.
        const explicit_types = new Map<string, 'kubenode' | 'datanode' | 'external'>()
        for (const r of port_results.value) {
            if (r.source_type != null) explicit_types.set(r.source_name, r.source_type)
            if (r.target_type != null) explicit_types.set(r.target_name, r.target_type)
        }

        // Pass 2: build unique NodeInfo entries, preferring explicit types from pass 1
        // and falling back to inference only when no explicit type was ever provided.
        const seen = new Map<string, NodeInfo>()
        for (const r of port_results.value) {
            if (!seen.has(r.source_name)) {
                seen.set(r.source_name, {
                    name: r.source_name,
                    ip:   r.source_ip,
                    type: explicit_types.get(r.source_name) ?? infer_node_type(r.source_name, port_results.value),
                })
            }
            if (!seen.has(r.target_name)) {
                seen.set(r.target_name, {
                    name: r.target_name,
                    ip:   r.target_ip,
                    type: explicit_types.get(r.target_name) ?? infer_node_type(r.target_name, port_results.value),
                })
            }
        }

        const nodes = Array.from(seen.values())
        nodes.sort((a, b) => a.name.localeCompare(b.name))
        return nodes
    })

    /** One SVG per physical node, rendered with the docs-style templates. */
    const all_node_svgs = computed((): { name: string; svg: string }[] => {
        return unique_nodes.value.map((node, index) => {
            // Results where this node is the target (incoming connections)
            const incoming = port_results.value.filter(r => r.target_name === node.name)
            const incoming_status = worst_status_per_port(incoming)

            // Results where this node is the source (outgoing connections)
            const outgoing = port_results.value.filter(r => r.source_name === node.name)
            const outgoing_status = worst_status_per_port(outgoing)

            // Clean up the node name so we can use it as an SVG filter ID suffix
            const id_suffix = `n${index}_${node.name.replace(/[^a-zA-Z0-9]/g, '_')}`

            // Use the right renderer depending on node type
            const raw_svg = node.type === 'datanode'
                ? render_datanode_svg(node.name, node.ip, incoming_status, outgoing_status, id_suffix)
                : node.type === 'external'
                    ? render_external_svg(node.name, node.ip, incoming_status, outgoing_status, id_suffix)
                    : render_kubenode_svg(node.name, node.ip, incoming_status, outgoing_status, id_suffix)

            // Defense-in-depth: sanitize SVG before v-html rendering.
            // The renderers already escape dynamic values via esc()/esc_attr(),
            // but DOMPurify catches anything a future renderer might miss.
            const svg = sanitize_svg(raw_svg)

            return { name: node.name, svg }
        })
    })

    return { unique_nodes, all_node_svgs }
}
