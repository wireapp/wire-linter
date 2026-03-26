// use_port_data.ts Vue composable that transforms raw DataPoint[] into structured
// port connectivity data for the PortsTab component.
//
// Works like use_result_trees.ts: takes a reactive ref to a flat data array and
// exposes computed properties that transform it. Keeps PortsTab.vue clean by
// extracting this data transformation logic and making it testable on its own.
//
// Exports from use_port_data(data_points):
//   port_results      computed list of PortCheckResult from port_connectivity data
//   firewall_data_map computed map of host name -> FirewallData from firewall_rules
//   total_port_count  computed total number of port connectivity results
//   open_count        computed number of open ports
//   closed_count      computed number of closed ports
//   filtered_count    computed number of filtered ports
//   tree_data         computed hierarchical SourceGroup[] tree (source -> target -> ports)

// External
import { computed, type Ref } from 'vue'

// Ours
import type { DataPoint } from '../sample-data'
import type { PortCheckResult, FirewallData, PortLink, TargetGroup, SourceGroup } from '../lib/port_types'

// Allowed firewall_type values from the FirewallData union
const valid_firewall_types = ['nftables', 'iptables', 'ufw', 'firewalld', 'none'] as const

/** Safely coerce a DataPoint value to a valid firewall type, defaulting to 'none'. */
function validate_firewall_type(value: string | number | boolean | null): FirewallData['firewall_type'] {
    if (typeof value === 'string' && (valid_firewall_types as readonly string[]).includes(value)) {
        return value as FirewallData['firewall_type']
    }
    return 'none'
}

/**
 * Transform a flat DataPoint[] into structured port connectivity data.
 *
 * Parses port_connectivity and firewall_rules data points, builds summary counts
 * and a three-level tree (source host -> target host -> ports) ready to use in
 * the PortsTab tree-table.
 *
 * @param data_points ref containing the flat list of collected data points
 * @returns port_results, firewall_data_map, summary counts, and tree_data
 */
export function use_port_data(data_points: Ref<DataPoint[]>) {
    // Data extraction

    // Parse per-port results from raw_output of port_connectivity data points
    const port_results = computed((): PortCheckResult[] => {
        const results: PortCheckResult[] = []

        for (const dp of data_points.value) {
            // Match data points from the port_connectivity target
            if (!/\/port_connectivity$/.test(dp.path)) continue

            // Structured data is in raw_output as PORT_RESULTS_JSON:{...}
            const raw = dp.raw_output ?? ''
            const json_prefix = 'PORT_RESULTS_JSON:'

            for (const line of raw.split('\n')) {
                const trimmed = line.trim()
                if (!trimmed.startsWith(json_prefix)) continue

                try {
                    const parsed = JSON.parse(trimmed.slice(json_prefix.length)) as PortCheckResult[]
                    results.push(...parsed)
                } catch {
                    // Malformed JSON, skip it
                }
            }
        }

        return results
    })

    // Parse firewall data from firewall_rules data points, keyed by host name
    const firewall_data_map = computed((): Map<string, FirewallData> => {
        const map = new Map<string, FirewallData>()

        for (const dp of data_points.value) {
            // Match data points from the firewall_rules target
            if (!/\/firewall_rules$/.test(dp.path)) continue

            const host_name = dp.metadata?.host_name as string | undefined
            const host_ip = dp.metadata?.host_ip as string | undefined
            if (!host_name) continue

            map.set(host_name, {
                host_name,
                host_ip:       host_ip ?? '',
                firewall_type: validate_firewall_type(dp.value),
                raw_rules:     dp.raw_output ?? '',
                rule_count:    (dp.raw_output ?? '').split('\n').filter(l => l.trim() && !l.trim().startsWith('#')).length,
            })
        }

        return map
    })

    // Summary counts

    const total_port_count = computed(() => port_results.value.length)

    const open_count = computed(() =>
        port_results.value.filter(r => r.status === 'open').length,
    )

    const closed_count = computed(() =>
        port_results.value.filter(r => r.status === 'closed').length,
    )

    const filtered_count = computed(() =>
        port_results.value.filter(r => r.status === 'filtered').length,
    )

    // Tree structure

    // Build the tree structure from port results: source -> target -> ports
    const tree_data = computed((): SourceGroup[] => {
        // Group by source host first
        const source_map = new Map<string, PortCheckResult[]>()

        for (const result of port_results.value) {
            const key = result.source_name
            const existing = source_map.get(key)
            if (existing) {
                existing.push(result)
            } else {
                source_map.set(key, [result])
            }
        }

        // Build source groups
        const groups: SourceGroup[] = []

        for (const [source_name, results] of source_map) {
            // Group within source by target host
            const target_map = new Map<string, PortCheckResult[]>()
            for (const r of results) {
                const tk = r.target_name
                const tex = target_map.get(tk)
                if (tex) {
                    tex.push(r)
                } else {
                    target_map.set(tk, [r])
                }
            }

            // Build target groups for this source
            const targets: TargetGroup[] = []
            for (const [target_name, target_results] of target_map) {
                const ports: PortLink[] = target_results.map(r => ({
                    id:          `${r.source_name}->${r.target_name}:${r.port}/${r.protocol}`,
                    source_name: r.source_name,
                    source_ip:   r.source_ip,
                    target_name: r.target_name,
                    target_ip:   r.target_ip,
                    port:        r.port,
                    protocol:    r.protocol,
                    service:     r.service,
                    status:      r.status,
                    latency_ms:  r.latency_ms,
                }))

                // Sort ports by number so they appear in order
                ports.sort((a, b) => a.port - b.port)

                const open = ports.filter(p => p.status === 'open').length

                targets.push({
                    key:   `${source_name}->${target_name}`,
                    name:  target_name,
                    ip:    target_results[0]?.target_ip ?? '',
                    open,
                    total: ports.length,
                    ports,
                })
            }

            // Alphabetize targets
            targets.sort((a, b) => a.name.localeCompare(b.name))

            const source_open = targets.reduce((sum, t) => sum + t.open, 0)
            const source_total = targets.reduce((sum, t) => sum + t.total, 0)

            groups.push({
                key:   source_name,
                name:  source_name,
                ip:    results[0]?.source_ip ?? '',
                open:  source_open,
                total: source_total,
                targets,
            })
        }

        // Alphabetize source groups
        groups.sort((a, b) => a.name.localeCompare(b.name))

        return groups
    })

    return {
        port_results,
        firewall_data_map,
        total_port_count,
        open_count,
        closed_count,
        filtered_count,
        tree_data,
    }
}
