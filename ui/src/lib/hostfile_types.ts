/**
 * Type definitions for Ansible host file (inventory) parsing.
 *
 * Extracted from hostfile_parser.ts to follow the pattern of separating
 * type definitions into dedicated *_types.ts files (firewall_types.ts, port_types.ts).
 * Lets consumers import just the types without dragging in the parser and js-yaml.
 */

// Parsed result from an Ansible inventory file (INI or YAML format)
// Host IPs grouped by Wire service, SSH credentials, and domain config
export interface ParsedHosts {
    // IP addresses extracted from each inventory group
    cassandra: string[]
    elasticsearch: string[]
    minio: string[]
    kubenode: string[]
    // Flattened lists: all unique kubenode IPs and all unique database IPs
    kube_nodes: string[]
    data_nodes: string[]
    // Admin host you SSH into (distinct from kubenodes in WIAB setups)
    admin_host: string
    // Variables extracted from [minio:vars], [all:vars], and host-level YAML vars
    domain: string
    ansible_user: string
    // SSH key on the local machine to reach the admin host (from YAML)
    ssh_key_path: string
    // SSH key on the admin host to reach cluster nodes (from INI)
    db_ssh_key: string
}

// Setup fields populated from a parsed host file
export interface HostfileSetupFields {
    cassandra_host: string
    elasticsearch_host: string
    minio_host: string
    admin_host_ip: string
    cluster_domain: string
    admin_user: string
    ssh_key_path: string
    // Database SSH jump host credentials (admin host to database VMs)
    db_ssh_user: string
    db_ssh_key: string
    // Explicit node IP lists for the nodes section
    kube_nodes: string[]
    data_nodes: string[]
}
