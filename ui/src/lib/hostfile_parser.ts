/**
 * Ansible host file (inventory) parser module.
 *
 * Parses both INI-format (hosts.ini) and YAML-format (inventory.yml)
 * Ansible inventories used by Wire deployments. Extracts host IPs
 * grouped by service (Cassandra, Elasticsearch, MinIO, Kubernetes)
 * along with SSH credentials and domain configuration.
 *
 * Functions:
 *   parse_hosts_ini parses [section]-based INI inventories
 *   parse_hosts_yaml parses YAML inventories (simple + children refs)
 *   merge_parsed_hosts merges INI + YAML parse results
 *   apply_parsed_hosts_to_setup maps parsed groups into a setup config object
 *
 * Exports:
 *   ParsedHosts interface for the parsed result
 */

// External
import yaml from 'js-yaml'

// Ours
import type { ParsedHosts, HostfileSetupFields } from './hostfile_types'

// Re-export types so existing consumers that import from this file still work
export type { ParsedHosts, HostfileSetupFields }

// Parsing functions

// Parse an Ansible INI inventory file (hosts.ini) and extract host IPs and variables.
// Wire's hosts.ini defines hosts in [all] with « ansible_host=IP », then groups
// them in sections like « [cassandra] », « [elasticsearch] », « [minio] », etc.
// Variables live in « [minio:vars] » (domain) and « [all:vars] » (ansible_user, ssh key).
export function parse_hosts_ini(ini_content: string): ParsedHosts {
    const result: ParsedHosts = {
        cassandra:      [],
        elasticsearch:  [],
        minio:          [],
        kubenode:       [],
        kube_nodes:     [],
        data_nodes:     [],
        admin_host:     '',
        domain:         '',
        ansible_user:   '',
        ssh_key_path:   '',
        db_ssh_key:     '',
    }

    const lines = ini_content.split('\n')

    // First pass: build a map of hostname -> ansible_host IP from [all] section
    const host_ip_map: Record<string, string> = {}
    let current_section = ''

    for (const raw_line of lines) {
        const line = raw_line.trim()

        // Skip empty lines and comments
        if (!line || line.startsWith('#') || line.startsWith(';')) continue

        // Detect section headers like [cassandra] or [minio:vars]
        const section_match = line.match(/^\[([^\]]+)\]$/)
        if (section_match) {
            current_section = section_match[1]!.toLowerCase()
            continue
        }

        // In [all] section, parse lines like « hostname ansible_host=X.X.X.X »
        if (current_section === 'all') {
            const host_match = line.match(/^(\S+)\s+.*ansible_host\s*=\s*(\S+)/)
            if (host_match) {
                host_ip_map[host_match[1]!] = host_match[2]!
            }
        }
    }

    // Second pass: resolve group memberships and extract variables
    current_section = ''

    for (const raw_line of lines) {
        const line = raw_line.trim()
        if (!line || line.startsWith('#') || line.startsWith(';')) continue

        const section_match = line.match(/^\[([^\]]+)\]$/)
        if (section_match) {
            current_section = section_match[1]!.toLowerCase()
            continue
        }

        // Collect hostnames from relevant group sections (skip :vars and :children)
        if (!current_section.includes(':')) {
            const hostname = line.split(/\s+/)[0]!
            const ip = host_ip_map[hostname]

            // Add the IP if we found it in the hostname map
            if (ip) {
                if (current_section === 'cassandra' && !result.cassandra.includes(ip)) {
                    result.cassandra.push(ip)
                } else if (current_section === 'elasticsearch' && !result.elasticsearch.includes(ip)) {
                    result.elasticsearch.push(ip)
                } else if (current_section === 'minio' && !result.minio.includes(ip)) {
                    result.minio.push(ip)
                } else if ((current_section === 'kube-node' || current_section === 'kubenode' || current_section === 'kube-master') && !result.kubenode.includes(ip)) {
                    result.kubenode.push(ip)
                }
            }
        }

        // Extract variables from :vars sections
        if (current_section === 'minio:vars') {
            const domain_match = line.match(/^domain\s*=\s*"?([^"]+)"?/)
            if (domain_match) result.domain = domain_match[1]!.trim()
        }

        if (current_section === 'all:vars') {
            const user_match = line.match(/^ansible_user\s*=\s*"?([^"]+)"?/)
            if (user_match) result.ansible_user = user_match[1]!.trim()

            // The path on the admin host for jumping to cluster nodes
            const key_match = line.match(/^ansible_ssh_private_key_file\s*=\s*"?([^"]+)"?/)
            if (key_match) result.db_ssh_key = key_match[1]!.trim()
        }
    }

    // Build flat node lists from the per-service arrays:
    // kube_nodes: all unique kubenode IPs (already deduplicated above)
    // data_nodes: union of all database service IPs, deduplicated
    result.kube_nodes = [...result.kubenode]
    result.data_nodes = [
        ...new Set([...result.cassandra, ...result.elasticsearch, ...result.minio]),
    ]

    // In multi-node INI deployments, the first kubenode doubles as admin host
    if (result.kubenode.length > 0) {
        result.admin_host = result.kubenode[0]!
    }

    return result
}

// Parse an Ansible YAML inventory file and extract host IPs and variables.
// Handles two formats:
//   1. Simple (wiab-staging.yml): single group with hosts containing ansible_host
//   2. Full (inventory.yml): multiple groups with children references
//      e.g. « cassandra.children.datanodes » resolves to « datanodes.hosts »
// Both formats store vars under group.vars and host-level ansible_* fields.
export function parse_hosts_yaml(yaml_content: string): ParsedHosts {
    const result: ParsedHosts = {
        cassandra:      [],
        elasticsearch:  [],
        minio:          [],
        kubenode:       [],
        kube_nodes:     [],
        data_nodes:     [],
        admin_host:     '',
        domain:         '',
        ansible_user:   '',
        ssh_key_path:   '',
        db_ssh_key:     '',
    }

    const doc = yaml.load(yaml_content) as Record<string, unknown> | null
    if (!doc || typeof doc !== 'object') return result

    type Group = Record<string, unknown>

    // Step 1: Build a map of group_name → list of ansible_host IPs.
    // Resolves both direct hosts and children references.
    const group_ips: Record<string, string[]> = {}

    // First pass: collect direct hosts for each group
    for (const [group_name, group_value] of Object.entries(doc)) {
        const group = group_value as Group
        if (!group || typeof group !== 'object') continue

        const hosts_section = group.hosts as Record<string, unknown> | undefined
        if (hosts_section && typeof hosts_section === 'object') {
            const ips: string[] = []
            for (const host_value of Object.values(hosts_section)) {
                const host = host_value as Record<string, unknown>
                if (!host || typeof host !== 'object') continue
                const ansible_host = String(host.ansible_host ?? '')
                if (ansible_host && !ips.includes(ansible_host)) {
                    ips.push(ansible_host)
                }
            }
            group_ips[group_name] = ips
        }
    }

    // Second pass: resolve children references. Groups like « cassandra »
    // that use « children: { datanodes: {} } » inherit the datanodes IPs.
    for (const [group_name, group_value] of Object.entries(doc)) {
        const group = group_value as Group
        if (!group || typeof group !== 'object') continue

        const children = group.children as Record<string, unknown> | undefined
        if (children && typeof children === 'object') {
            const resolved: string[] = group_ips[group_name] ?? []
            for (const child_name of Object.keys(children)) {
                const child_ips = group_ips[child_name] ?? []
                for (const ip of child_ips) {
                    if (!resolved.includes(ip)) resolved.push(ip)
                }
            }
            group_ips[group_name] = resolved
        }
    }

    // Step 2: Map known Wire group names to result fields
    const group_mapping: Record<string, keyof Pick<ParsedHosts, 'cassandra' | 'elasticsearch' | 'minio' | 'kubenode'>> = {
        'cassandra':     'cassandra',
        'elasticsearch': 'elasticsearch',
        'minio':         'minio',
        'kube-node':     'kubenode',
        'kubenode':      'kubenode',
        'kube-master':   'kubenode',
    }

    for (const [group_name, field] of Object.entries(group_mapping)) {
        const ips = group_ips[group_name] ?? []
        for (const ip of ips) {
            if (!result[field].includes(ip)) {
                result[field].push(ip)
            }
        }
    }

    // Step 3: Extract SSH credentials and domain from vars sections.
    // Checks « all » group vars first, then host-level vars as fallback.
    for (const [_group_name, group_value] of Object.entries(doc)) {
        const group = group_value as Group
        if (!group || typeof group !== 'object') continue

        // Group-level vars
        const vars_section = group.vars as Record<string, unknown> | undefined
        if (vars_section && typeof vars_section === 'object') {
            if (vars_section.ansible_user && !result.ansible_user) {
                result.ansible_user = String(vars_section.ansible_user)
            }
            if (vars_section.ansible_ssh_private_key_file && !result.ssh_key_path) {
                result.ssh_key_path = String(vars_section.ansible_ssh_private_key_file)
            }
            if (vars_section.target_domain && !result.domain) {
                result.domain = String(vars_section.target_domain)
            }
            if (vars_section.domain && !result.domain) {
                result.domain = String(vars_section.domain)
            }
        }

        // Host-level vars (e.g. wiab-staging format with ansible_user on the host)
        const hosts_section = group.hosts as Record<string, unknown> | undefined
        if (hosts_section && typeof hosts_section === 'object') {
            for (const host_value of Object.values(hosts_section)) {
                const host = host_value as Record<string, unknown>
                if (!host || typeof host !== 'object') continue
                if (host.ansible_user && !result.ansible_user) {
                    result.ansible_user = String(host.ansible_user)
                }
                if (host.ansible_ssh_private_key_file && !result.ssh_key_path) {
                    result.ssh_key_path = String(host.ansible_ssh_private_key_file)
                }
            }
        }
    }

    // Step 4: Set the admin host.
    // For full inventories with kube groups, use the first kubenode.
    // For WIAB (single host), use whatever host we found.
    if (result.kubenode.length > 0) {
        result.admin_host = result.kubenode[0]!
    } else {
        // Single-host case: grab the first IP we found
        for (const ips of Object.values(group_ips)) {
            if (ips.length > 0) {
                result.admin_host = ips[0]!
                break
            }
        }
    }

    // Build flat node lists from the per-service arrays
    result.kube_nodes = [...result.kubenode]
    result.data_nodes = [
        ...new Set([...result.cassandra, ...result.elasticsearch, ...result.minio]),
    ]

    return result
}

// Merge two ParsedHosts results into one, combining arrays (deduplicated)
// and preferring the first non-empty string for scalar fields.
// Called when both INI and YAML host files are provided.
export function merge_parsed_hosts(a: ParsedHosts, b: ParsedHosts): ParsedHosts {
    // Combine two string arrays, keeping only unique values
    const merge_unique = (left: string[], right: string[]): string[] => {
        return [...new Set([...left, ...right])]
    }

    return {
        cassandra:      merge_unique(a.cassandra, b.cassandra),
        elasticsearch:  merge_unique(a.elasticsearch, b.elasticsearch),
        minio:          merge_unique(a.minio, b.minio),
        kubenode:       merge_unique(a.kubenode, b.kubenode),
        kube_nodes:     merge_unique(a.kube_nodes, b.kube_nodes),
        data_nodes:     merge_unique(a.data_nodes, b.data_nodes),
        // Connection fields: prefer YAML (b) it has the external hostname/key
        // to reach the cluster from outside, INI just has internal cluster IPs
        admin_host:     b.admin_host || a.admin_host,
        ansible_user:   b.ansible_user || a.ansible_user,
        ssh_key_path:   b.ssh_key_path || a.ssh_key_path,
        // Topology fields: prefer INI (a) it has the full cluster layout
        domain:         a.domain || b.domain,
        db_ssh_key:     a.db_ssh_key || b.db_ssh_key,
    }
}

// Apply parsed host file data to the configuration form fields.
// Takes the setup object directly, stays Vue-independent.
export function apply_parsed_hosts_to_setup(hosts: ParsedHosts, setup: HostfileSetupFields): void {
    // Use the first IP from each group as the primary host address
    if (hosts.cassandra.length)     setup.cassandra_host     = hosts.cassandra[0]!
    if (hosts.elasticsearch.length) setup.elasticsearch_host = hosts.elasticsearch[0]!
    if (hosts.minio.length)         setup.minio_host         = hosts.minio[0]!

    // Admin host: explicit field, or fall back to first kubenode
    if (hosts.admin_host)           setup.admin_host_ip      = hosts.admin_host
    else if (hosts.kubenode.length) setup.admin_host_ip      = hosts.kubenode[0]!

    // Node lists for the nodes configuration section
    if (hosts.kube_nodes.length)    setup.kube_nodes         = [...hosts.kube_nodes]
    if (hosts.data_nodes.length)    setup.data_nodes         = [...hosts.data_nodes]

    // Domain maps to cluster domain
    if (hosts.domain)               setup.cluster_domain     = hosts.domain

    // SSH settings
    if (hosts.ansible_user)         setup.admin_user         = hosts.ansible_user
    if (hosts.ansible_user)         setup.db_ssh_user        = hosts.ansible_user
    // Local key from YAML (this machine to admin host)
    if (hosts.ssh_key_path)         setup.ssh_key_path       = hosts.ssh_key_path
    // Jump key from INI (admin host to cluster nodes), falls back to local key
    if (hosts.db_ssh_key)           setup.db_ssh_key         = hosts.db_ssh_key
    else if (hosts.ssh_key_path)    setup.db_ssh_key         = hosts.ssh_key_path
}
