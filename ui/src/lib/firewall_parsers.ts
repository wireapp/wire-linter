// Firewall rule parser converts « iptables-save » and « nft list ruleset » output
// into typed arrays. Just parsing, nothing else data goes one way in, typed rules out.

// Ours
import type { IptablesRule, NftablesRule } from './firewall_types'

// ---------------------------------------------------------------------------
// iptables parsing
// ---------------------------------------------------------------------------

// Parse « iptables-save » output finds all rules and chain defaults.
// Lines starting with « * » are tables, « : » are chain policies, « -A » are rules, « COMMIT » ends blocks.
export function parse_iptables_rules(raw: string): IptablesRule[] {
    // Empty input, bail early
    if (!raw || !raw.trim()) return []

    const rules: IptablesRule[] = []
    const lines = raw.split('\n')

    let current_table = 'filter'

    for (let line_index = 0; line_index < lines.length; line_index++) {
        const raw_line = lines[line_index]
        if (raw_line === undefined) continue

        const line = raw_line.trim()

        // Skip empty lines and comments
        if (!line || line.startsWith('#')) continue

        // Table declaration: « *filter », « *nat », etc.
        if (line.startsWith('*')) {
            current_table = line.slice(1)
            continue
        }

        if (line === 'COMMIT') continue

        // Chain default policy: « :INPUT DROP [0:0] »
        if (line.startsWith(':')) {
            const policy_rule = parse_iptables_chain_policy(line, current_table, line_index + 1)
            if (policy_rule) rules.push(policy_rule)
            continue
        }

        // Explicit rule: « -A INPUT -p tcp --dport 9042 -j DROP »
        if (line.startsWith('-A')) {
            const rule = parse_iptables_rule_line(line, current_table, line_index + 1)
            if (rule) rules.push(rule)
        }
    }

    return rules
}

// Chain policy line parser catches the default action when no explicit rules match
function parse_iptables_chain_policy(
    line: string,
    table: string,
    line_number: number,
): IptablesRule | null {
    const match = line.match(/^:(\S+)\s+(ACCEPT|DROP|REJECT)/)
    if (!match || !match[1] || !match[2]) return null

    return {
        line_number,
        raw:    line,
        chain:  match[1],
        table,
        target: match[2],
    }
}

// Parse a single rule line from « iptables-save »
function parse_iptables_rule_line(
    line: string,
    table: string,
    line_number: number,
): IptablesRule | null {
    const chain_match = line.match(/^-A\s+(\S+)/)
    if (!chain_match || !chain_match[1]) return null

    const rule: IptablesRule = {
        line_number,
        raw:    line,
        chain:  chain_match[1],
        table,
        target: '',
    }

    const proto_match = line.match(/-p\s+(\S+)/)
    if (proto_match && proto_match[1]) {
        rule.protocol = proto_match[1].toLowerCase()
    }

    // Multiport extension: « --dports 80,443,8080 » or « --dports 1000:2000 »
    const dports_match = line.match(/--dports\s+(\S+)/)
    if (dports_match && dports_match[1]) {
        const elements = dports_match[1].split(',').map((s) => s.trim()).filter(Boolean)
        const dports: number[] = []
        for (const element of elements) {
            // Colon-range within multiport list: « 1000:2000 »
            const range_parts = element.match(/^(\d+):(\d+)$/)
            if (range_parts && range_parts[1] && range_parts[2]) {
                rule.dport     = parseInt(range_parts[1], 10)
                rule.dport_end = parseInt(range_parts[2], 10)
            } else {
                const port_num = parseInt(element, 10)
                if (!isNaN(port_num)) dports.push(port_num)
            }
        }
        if (dports.length > 0) rule.dports = dports
    } else {
        // Single port or colon range: « --dport 9042 » or « --dport 1000:2000 »
        const dport_match = line.match(/--dport\s+(\d+)(?::(\d+))?/)
        if (dport_match && dport_match[1]) {
            rule.dport = parseInt(dport_match[1], 10)
            if (dport_match[2]) {
                rule.dport_end = parseInt(dport_match[2], 10)
            }
        }
    }

    const sport_match = line.match(/--sport\s+(\d+)/)
    if (sport_match && sport_match[1]) {
        rule.sport = parseInt(sport_match[1], 10)
    }

    const source_match = line.match(/-s\s+(\S+)/)
    if (source_match && source_match[1]) {
        rule.source = source_match[1]
    }

    const dest_match = line.match(/-d\s+(\S+)/)
    if (dest_match && dest_match[1]) {
        rule.destination = dest_match[1]
    }

    const target_match = line.match(/-j\s+(\S+)/)
    if (target_match && target_match[1]) {
        rule.target = target_match[1]
    }

    return rule
}

// ---------------------------------------------------------------------------
// nftables parsing
// ---------------------------------------------------------------------------

// Parse « nft list ruleset » output handles nested table/chain structure
export function parse_nftables_rules(raw: string): NftablesRule[] {
    // Empty input, bail early
    if (!raw || !raw.trim()) return []

    const rules: NftablesRule[] = []
    const lines = raw.split('\n')

    let current_table = ''
    let current_chain = ''
    // Numeric depth counter: 0=top-level, 1=inside table, 2=inside chain/set/map, 3+=nested elements/sub-blocks.
    // Using depth instead of string-emptiness checks prevents nested set/map/elements braces from
    // prematurely clearing current_table or current_chain (the bug that occurred before this fix).
    let brace_depth = 0

    for (let line_index = 0; line_index < lines.length; line_index++) {
        const raw_line = lines[line_index]
        if (raw_line === undefined) continue

        const line = raw_line.trim()

        // Skip empty lines and comments
        if (!line || line.startsWith('#')) continue

        // Table opening: « table inet filter { »
        const table_match = line.match(/^table\s+(\S+\s+\S+)\s*\{/)
        if (table_match && table_match[1]) {
            current_table = table_match[1]
            brace_depth++
            continue
        }

        // Chain opening: « chain input { »
        const chain_match = line.match(/^chain\s+(\S+)\s*\{/)
        if (chain_match && chain_match[1]) {
            current_chain = chain_match[1]
            brace_depth++
            continue
        }

        // Count net braces on this line to handle: standalone « } », « set/map foo { », « elements = { », etc.
        // Lines with balanced braces (e.g. « ip saddr { 10.0.0.1 } accept ») have net=0 and fall through to rule parsing.
        const open_count  = (line.match(/\{/g) ?? []).length
        const close_count = (line.match(/\}/g) ?? []).length

        if (open_count !== close_count) {
            brace_depth += open_count - close_count
            if (brace_depth <= 0) {
                // Outermost table scope closed
                current_table = ''
                current_chain = ''
                brace_depth   = 0
            } else if (brace_depth === 1) {
                // Returned to table level: a chain or set/map directly under the table just closed
                current_chain = ''
            }
            // Depth 2+ close means a nested elements/sub-block closed; no scope state to clear
            continue
        }

        // Chain policy default action
        const policy_match = line.match(/policy\s+(accept|drop|reject)\s*;/)
        if (policy_match && policy_match[1] && current_chain) {
            rules.push({
                line_number: line_index + 1,
                raw:         line,
                table:       current_table,
                chain:       current_chain,
                verdict:     policy_match[1],
            })
            continue
        }

        // Extract rules by verdict keyword
        const verdict_match = line.match(/\b(accept|drop|reject)\b/)
        if (verdict_match && verdict_match[1] && current_chain) {
            const rule: NftablesRule = {
                line_number: line_index + 1,
                raw:         line,
                table:       current_table,
                chain:       current_chain,
                verdict:     verdict_match[1],
            }

            const proto_match = line.match(/\b(tcp|udp)\b/)
            if (proto_match && proto_match[1]) {
                rule.protocol = proto_match[1]
            }

            // Try set syntax first: « dport { 80, 443 } » or « dport { 1024-65535 } »
            const dport_set_match = line.match(/dport\s+\{([^}]+)\}/)
            if (dport_set_match && dport_set_match[1]) {
                const elements = dport_set_match[1].split(',').map((s) => s.trim()).filter(Boolean)
                const dports: number[] = []
                for (const element of elements) {
                    // Range element: « 1024-65535 »
                    const range_parts = element.match(/^(\d+)-(\d+)$/)
                    if (range_parts && range_parts[1] && range_parts[2]) {
                        rule.dport     = parseInt(range_parts[1], 10)
                        rule.dport_end = parseInt(range_parts[2], 10)
                    } else {
                        const port_num = parseInt(element, 10)
                        if (!isNaN(port_num)) dports.push(port_num)
                    }
                }
                if (dports.length > 0) rule.dports = dports
            } else {
                // Plain single port or range: « dport 443 » or « dport 1024-2048 »
                const dport_match = line.match(/dport\s+(\d+)(?:-(\d+))?/)
                if (dport_match && dport_match[1]) {
                    rule.dport = parseInt(dport_match[1], 10)
                    if (dport_match[2]) {
                        rule.dport_end = parseInt(dport_match[2], 10)
                    }
                }
            }

            // Set syntax comes before single-address check: « saddr { 10.0.0.1, 10.0.0.2 } » would
            // otherwise have « { » captured as the address by the \S+ pattern below
            const saddr_set_match = line.match(/saddr\s+\{([^}]+)\}/)
            if (saddr_set_match && saddr_set_match[1]) {
                rule.source = saddr_set_match[1].trim()
            } else {
                const saddr_match = line.match(/saddr\s+(\S+)/)
                if (saddr_match && saddr_match[1]) {
                    rule.source = saddr_match[1]
                }
            }

            const daddr_set_match = line.match(/daddr\s+\{([^}]+)\}/)
            if (daddr_set_match && daddr_set_match[1]) {
                rule.destination = daddr_set_match[1].trim()
            } else {
                const daddr_match = line.match(/daddr\s+(\S+)/)
                if (daddr_match && daddr_match[1]) {
                    rule.destination = daddr_match[1]
                }
            }

            rules.push(rule)
        }
    }

    return rules
}
