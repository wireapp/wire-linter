/**
 * Port connectivity types what gets collected from Python, what gets displayed.
 *
 * PortCheckResult: raw connectivity test result
 * FirewallData: parsed firewall state for one host
 * PortLink: flattened row for the tree-table view
 * NodeInfo: node identity for the diagram
 * PortDefinition: one port in the expected-connectivity matrix
 * PortCategory: a group of expected ports between two host types
 */

// Collected data structures

/** Single port connectivity test result from the Python gatherer. */
export interface PortCheckResult {
    source_name: string
    source_ip: string

    // Node type of the source host, provided by the gatherer
    source_type?: 'kubenode' | 'datanode' | 'external'

    target_name: string
    target_ip: string

    // Node type of the target host, provided by the gatherer
    target_type?: 'kubenode' | 'datanode' | 'external'

    port: number
    protocol: 'tcp' | 'udp'

    // e.g. «Cassandra CQL», «Kubernetes API»
    service: string

    status: 'open' | 'closed' | 'filtered' | 'error'

    // Only present if reachable
    latency_ms?: number
}

/** Parsed firewall configuration for a single host. */
export interface FirewallData {
    host_name: string
    host_ip: string

    firewall_type: 'nftables' | 'iptables' | 'ufw' | 'firewalld' | 'none'

    // Raw output from firewall dump
    raw_rules: string

    rule_count: number
}

// Display / UI structures

/** Single port-connectivity row for the tree-table or list view. */
export interface PortLink {
    id: string

    source_name: string
    source_ip: string

    target_name: string
    target_ip: string

    port: number
    protocol: string
    service: string

    status: 'open' | 'closed' | 'filtered' | 'error'

    latency_ms?: number
}

/** Group of ports to a single target host in the source→target→port tree. */
export interface TargetGroup {
    key: string

    name: string
    ip: string

    open: number
    total: number

    ports: PortLink[]
}

/** Top-level source host group containing all its target groups. */
export interface SourceGroup {
    key: string

    name: string
    ip: string

    open: number
    total: number

    targets: TargetGroup[]
}

/** Node identity for the network diagram. */
export interface NodeInfo {
    // e.g. «kubenode-1», «datanode-cassandra-0»
    name: string

    ip: string

    type: 'kubenode' | 'datanode' | 'external'
}

// Port matrix structures

/** Single expected port in the connectivity matrix. */
export interface PortDefinition {
    port: number

    protocol: 'tcp' | 'udp'

    service: string
}

/** Group of expected ports between two host types. */
export interface PortCategory {
    source_type: 'kubenode' | 'datanode' | 'external'

    target_type: 'kubenode' | 'datanode' | 'external'

    // e.g. «Kubenode -> Datanode»
    label: string

    ports: PortDefinition[]
}
