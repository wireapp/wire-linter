// Analyzes firewall rules to explain why a port might be blocked.
// Searches parsed firewall rules for entries that would block a specific port,
// then generates a human-readable explanation plus the exact command to fix it.
// Raw firewall text is parsed by firewall_parsers.ts.
//
// Supports: iptables, nftables, ufw, firewalld

// Ours
import type { FirewallData } from './port_types'
import type { BlockingRuleAnalysis } from './firewall_types'
import { ip_in_cidr } from './cidr_utils'
import { parse_iptables_rules, parse_nftables_rules } from './firewall_parsers'

// Re-export the types so existing consumers of firewall_analyzer still work
export type { IptablesRule, NftablesRule, BlockingRuleAnalysis } from './firewall_types'

// Re-export parsers so existing consumers that imported them from here still work
export { parse_iptables_rules, parse_nftables_rules } from './firewall_parsers'

// ---------------------------------------------------------------------------
// Blocking rule analysis
// ---------------------------------------------------------------------------

// Search a host's firewall rules for the one that blocks a specific port.
// Checks both explicit DROP/REJECT rules targeting the port and default
// chain policies that would block unmatched traffic. Returns null if no
// blocking rule is found (meaning the firewall isn't the cause).
//
// firewall_data: Parsed firewall state for the host
// remote_ip: IP of the remote host (target for incoming, source for outgoing)
// port: The port number that failed connectivity
// protocol: Transport protocol «tcp» or «udp»
// direction: Whether to check incoming (INPUT/FORWARD) or outgoing (OUTPUT) chains
export function find_blocking_rule(
    firewall_data: FirewallData,
    remote_ip: string,
    port: number,
    protocol: string,
    direction: 'incoming' | 'outgoing' = 'incoming',
): BlockingRuleAnalysis | null {
    // No firewall, nothing to check
    if (firewall_data.firewall_type === 'none') return null

    // If there's no raw rules, we have nothing to analyze
    if (!firewall_data.raw_rules || !firewall_data.raw_rules.trim()) return null

    // Route to the right parser based on firewall type
    if (firewall_data.firewall_type === 'iptables' || firewall_data.firewall_type === 'ufw') {
        // ufw wraps iptables, so we get iptables-save format
        return find_blocking_iptables_rule(firewall_data, remote_ip, port, protocol, direction)
    }

    if (firewall_data.firewall_type === 'nftables') {
        return find_blocking_nftables_rule(firewall_data, remote_ip, port, protocol, direction)
    }

    if (firewall_data.firewall_type === 'firewalld') {
        // firewalld can use iptables or nftables as its backend, try both
        const iptables_result = find_blocking_iptables_rule(firewall_data, remote_ip, port, protocol, direction)
        if (iptables_result) return iptables_result

        return find_blocking_nftables_rule(firewall_data, remote_ip, port, protocol, direction)
    }

    return null
}

// Search iptables rules for a DROP/REJECT that blocks the given port.
// We check explicit port-specific rules first, then fall back to default
// chain policies, which block everything not explicitly allowed.
function find_blocking_iptables_rule(
    firewall_data: FirewallData,
    remote_ip: string,
    port: number,
    protocol: string,
    direction: 'incoming' | 'outgoing' = 'incoming',
): BlockingRuleAnalysis | null {
    const rules = parse_iptables_rules(firewall_data.raw_rules)
    const fix_command = generate_fix_command(firewall_data, remote_ip, port, protocol, direction)

    // Pick which chains to check based on traffic direction
    const relevant_chains = direction === 'incoming'
        ? ['INPUT', 'FORWARD']
        : ['OUTPUT', 'FORWARD']

    // First pass, look for explicit DROP/REJECT rules matching this port
    for (const rule of rules) {
        // Only interested in blocking actions
        const is_blocking = rule.target === 'DROP' || rule.target === 'REJECT'
        if (!is_blocking) continue

        // Skip chain default policy lines (they start with «:»), we handle those below
        if (rule.raw.startsWith(':')) continue

        // Check if this rule targets our specific port. A rule with no port filter matches all.
        // Handles single port, colon range (dport/dport_end), and multiport sets (dports).
        const has_no_port_filter    = rule.dport === undefined && !rule.dports
        const covers_port_via_set   = rule.dports !== undefined && rule.dports.includes(port)
        const covers_port_via_range = rule.dport  !== undefined && (
            rule.dport <= port && (rule.dport_end ?? rule.dport) >= port
        )
        const matches_port = has_no_port_filter || covers_port_via_set || covers_port_via_range
        // Protocol match, or no protocol filter means it matches everything
        const matches_protocol = !rule.protocol || rule.protocol === protocol.toLowerCase()
        // Rule needs to be in a chain we care about
        const is_relevant_chain = relevant_chains.includes(rule.chain)
        // For incoming, remote_ip is the source; for outgoing, it's the destination.
        // If the rule has no address filter, it matches all IPs. If it does have a filter,
        // remote_ip must be within that filter for us to consider it matching.
        const matches_remote_ip = direction === 'incoming'
            ? (!rule.source      || ip_in_cidr(remote_ip, rule.source))
            : (!rule.destination || ip_in_cidr(remote_ip, rule.destination))

        if (matches_port && matches_protocol && is_relevant_chain && matches_remote_ip) {
            return {
                rule_text:        rule.raw,
                rule_line_number: rule.line_number,
                chain:            rule.chain,
                table:            rule.table,
                explanation:      `Explicit ${rule.target} rule in ${rule.chain} chain blocks ${protocol.toUpperCase()} port ${port}`,
                fix_command,
            }
        }
    }

    // Second pass, check if a default DROP/REJECT policy would catch this port.
    // Only matters if there's no ACCEPT rule that would let this port through
    const has_accept_for_port = rules.some((rule) => {
        if (rule.target !== 'ACCEPT') return false
        // If any port filter is present (dport or dports), it must cover the target port
        const covers_via_set   = rule.dports !== undefined && rule.dports.includes(port)
        const covers_via_range = rule.dport  !== undefined && (rule.dport <= port && (rule.dport_end ?? rule.dport) >= port)
        if ((rule.dport !== undefined || rule.dports !== undefined) && !covers_via_set && !covers_via_range) return false
        if (rule.protocol && rule.protocol !== protocol.toLowerCase())   return false
        if (!relevant_chains.includes(rule.chain))                       return false
        // The ACCEPT rule needs to cover remote_ip. An ACCEPT rule scoped to a
        // different subnet shouldn't suppress the default-policy check for remote_ip.
        const covers_remote_ip = direction === 'incoming'
            ? (!rule.source      || ip_in_cidr(remote_ip, rule.source))
            : (!rule.destination || ip_in_cidr(remote_ip, rule.destination))
        return covers_remote_ip
    })

    if (!has_accept_for_port) {
        // Look for default chain policies that would block
        for (const rule of rules) {
            // Default policies are in lines like «:CHAIN POLICY»
            if (!rule.raw.startsWith(':')) continue

            const is_blocking = rule.target === 'DROP' || rule.target === 'REJECT'
            // Need to be in a relevant chain for the traffic direction
            const is_relevant_chain = relevant_chains.includes(rule.chain)

            if (is_blocking && is_relevant_chain) {
                return {
                    rule_text:        rule.raw,
                    rule_line_number: rule.line_number,
                    chain:            rule.chain,
                    table:            rule.table,
                    explanation:      `Default ${rule.target} policy on ${rule.chain} chain blocks all unmatched traffic including ${protocol.toUpperCase()} port ${port}`,
                    fix_command,
                }
            }
        }
    }

    return null
}

// Search nftables rules for a drop/reject that blocks the given port.
// Same strategy as iptables, check explicit port rules first,
// then fall back to chain policies.
function find_blocking_nftables_rule(
    firewall_data: FirewallData,
    remote_ip: string,
    port: number,
    protocol: string,
    direction: 'incoming' | 'outgoing' = 'incoming',
): BlockingRuleAnalysis | null {
    const rules = parse_nftables_rules(firewall_data.raw_rules)
    const fix_command = generate_fix_command(firewall_data, remote_ip, port, protocol, direction)

    // Pick relevant chains based on traffic direction
    const relevant_chains = direction === 'incoming'
        ? ['input', 'forward']
        : ['output', 'forward']

    // First pass, explicit port-specific drop/reject rules
    for (const rule of rules) {
        const is_blocking = rule.verdict === 'drop' || rule.verdict === 'reject'
        if (!is_blocking) continue

        // Skip policy lines (they say «policy drop;» but have no port info)
        if (rule.raw.includes('policy')) continue

        // Check port match: no filter covers all ports; set syntax checked via dports;
        // single/range checked via dport/dport_end.
        const has_no_port_filter    = rule.dport === undefined && !rule.dports
        const covers_port_via_set   = rule.dports !== undefined && rule.dports.includes(port)
        const covers_port_via_range = rule.dport !== undefined && (
            rule.dport_end !== undefined ? port >= rule.dport && port <= rule.dport_end : rule.dport === port
        )
        const matches_port = has_no_port_filter || covers_port_via_set || covers_port_via_range
        // Protocol match, or no protocol filter means it matches all
        const matches_protocol = !rule.protocol || rule.protocol === protocol.toLowerCase()

        const is_relevant_chain = relevant_chains.includes(rule.chain?.toLowerCase() ?? '')
        // nftables splits into saddr (source) and daddr (destination).
        // For incoming traffic, remote_ip is the source, check rule.source.
        // For outgoing, remote_ip is the destination, check rule.destination.
        // No address filter means the rule matches all IPs.
        const matches_remote_ip = direction === 'incoming'
            ? (!rule.source      || ip_in_cidr(remote_ip, rule.source))
            : (!rule.destination || ip_in_cidr(remote_ip, rule.destination))

        if (matches_port && matches_protocol && is_relevant_chain && matches_remote_ip) {
            return {
                rule_text:        rule.raw,
                rule_line_number: rule.line_number,
                chain:            rule.chain,
                table:            rule.table,
                explanation:      `Explicit ${rule.verdict} rule in ${rule.chain} chain blocks ${protocol.toUpperCase()} port ${port}`,
                fix_command,
            }
        }
    }

    // Second pass, check if default policies would block.
    // The accept rule needs to cover remote_ip. An accept scoped to
    // a different subnet shouldn't suppress the default-policy check.
    const has_accept_for_port = rules.some((rule) => {
        if (rule.verdict !== 'accept')                                   return false
        // If any port filter is present (dport or dports), it must cover the target port
        const covers_via_set   = rule.dports !== undefined && rule.dports.includes(port)
        const covers_via_range = rule.dport  !== undefined && (rule.dport <= port && (rule.dport_end ?? rule.dport) >= port)
        if ((rule.dport !== undefined || rule.dports !== undefined) && !covers_via_set && !covers_via_range) return false
        if (rule.protocol && rule.protocol !== protocol.toLowerCase())   return false
        if (!relevant_chains.includes(rule.chain?.toLowerCase() ?? '')) return false
        const covers_remote_ip = direction === 'incoming'
            ? (!rule.source      || ip_in_cidr(remote_ip, rule.source))
            : (!rule.destination || ip_in_cidr(remote_ip, rule.destination))
        return covers_remote_ip
    })

    if (!has_accept_for_port) {
        // Look for default policy lines like «policy drop;» or «policy reject;»
        for (const rule of rules) {
            if (!rule.raw.includes('policy')) continue

            const is_blocking = rule.verdict === 'drop' || rule.verdict === 'reject'
            // Need to be in a relevant chain for the traffic direction
            const is_relevant_chain = relevant_chains.includes(rule.chain?.toLowerCase() ?? '')

            if (is_blocking && is_relevant_chain) {
                return {
                    rule_text:        rule.raw,
                    rule_line_number: rule.line_number,
                    chain:            rule.chain,
                    table:            rule.table,
                    explanation:      `Default ${rule.verdict} policy on ${rule.chain} chain blocks all unmatched traffic including ${protocol.toUpperCase()} port ${port}`,
                    fix_command,
                }
            }
        }
    }

    return null
}

// ---------------------------------------------------------------------------
// Shell escaping
// ---------------------------------------------------------------------------

// Escape a value for safe interpolation into a shell command string.
// Wraps the value in single quotes and escapes any embedded single quotes
// using the standard POSIX trick: end the current single-quoted string,
// insert a backslash-escaped literal quote, then re-open a new single-quoted
// string. For example, O'Brien becomes 'O'\''Brien'.
function shell_escape(value: string | number): string {
    const str = String(value)

    // Replace each single quote with the end-quote + escaped-quote + start-quote sequence
    return "'" + str.replace(/'/g, "'\\''") + "'"
}

// ---------------------------------------------------------------------------
// Fix command generation
// ---------------------------------------------------------------------------

// Generate the shell command to allow a blocked port through the firewall.
// Picks the right command for the detected firewall type. All commands use
// sudo since firewall changes need root privileges.
//
// All dynamic values are shell-escaped before interpolation to prevent
// command injection from maliciously crafted JSONL input.
//
// firewall_data: Firewall state, used to pick which tool to target
// remote_ip: Remote IP to allow (source for incoming, destination for outgoing)
// port: Port number to open
// protocol: Transport protocol «tcp» or «udp»
// direction: Whether the block is on incoming or outgoing traffic
export function generate_fix_command(
    firewall_data: FirewallData,
    remote_ip: string,
    port: number,
    protocol: string,
    direction: 'incoming' | 'outgoing' = 'incoming',
): string {
    // Shell-escape all dynamic values to prevent command injection
    const safe_proto = shell_escape(protocol.toLowerCase())
    const safe_ip = shell_escape(remote_ip)
    const safe_port = shell_escape(port)

    // Figure out the chain name based on traffic direction
    const iptables_chain = direction === 'incoming' ? 'INPUT' : 'OUTPUT'
    const nftables_chain = direction === 'incoming' ? 'input' : 'output'

    switch (firewall_data.firewall_type) {
        case 'iptables':
            // Insert at the top of the chain so it takes precedence over later DROP rules
            return direction === 'incoming'
                ? `sudo iptables -I ${iptables_chain} -p ${safe_proto} -s ${safe_ip} --dport ${safe_port} -j ACCEPT`
                : `sudo iptables -I ${iptables_chain} -p ${safe_proto} -d ${safe_ip} --dport ${safe_port} -j ACCEPT`

        case 'nftables':
            // Add an accept rule to the inet filter chain
            return `sudo nft add rule inet filter ${nftables_chain} ${safe_proto} dport ${safe_port} accept`

        case 'ufw':
            // ufw has simpler syntax, direction is handled by allow in/out
            return direction === 'incoming'
                ? `sudo ufw allow ${safe_port}/${safe_proto}`
                : `sudo ufw allow out ${safe_port}/${safe_proto}`

        case 'firewalld':
            // firewalld needs --permanent plus a reload to actually save the change
            // --add-port only opens incoming traffic; outgoing requires the direct interface
            return direction === 'incoming'
                ? `sudo firewall-cmd --permanent --add-port=${safe_port}/${safe_proto} && sudo firewall-cmd --reload`
                : `sudo firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p ${safe_proto} --dport ${safe_port} -j ACCEPT && sudo firewall-cmd --reload`

        case 'none':
            // No firewall detected, nothing to fix on the firewall side
            return `# No firewall detected on ${shell_escape(firewall_data.host_name)}, port ${safe_port}/${safe_proto} should not be blocked by local rules`
    }
}
