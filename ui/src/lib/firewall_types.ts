// Types for firewall rules (iptables/nftables) and analysis results

// Parsed iptables rule
export interface IptablesRule {
    line_number: number      // 1-based in output
    raw: string              // full rule text
    chain: string            // INPUT, FORWARD, OUTPUT, etc.
    table: string            // filter, nat, mangle, raw
    protocol?: string        // tcp, udp, icmp
    dport?: number           // e.g., start of « 9000:9999 »
    dport_end?: number       // end of port range
    dports?: number[]        // explicit port set from « --dports 80,443,8080 » (multiport extension)
    sport?: number           // source port
    source?: string          // source IP/CIDR
    destination?: string     // dest IP/CIDR
    target: string           // ACCEPT, DROP, REJECT, etc.
}

// Parsed nftables rule
export interface NftablesRule {
    line_number: number      // 1-based in output
    raw: string              // full rule text
    table: string            // e.g., « inet filter », « ip nat »
    chain: string            // e.g., « input », « forward »
    protocol?: string        // tcp, udp
    dport?: number           // start of « 9000-9999 » or single port
    dport_end?: number       // end of port range
    dports?: number[]        // explicit port set from « dport { 80, 443, 8080 } »
    source?: string          // source address
    destination?: string     // dest address
    verdict: string          // accept, drop, reject
}

// Analysis result when a rule blocks a port
export interface BlockingRuleAnalysis {
    rule_text: string         // the blocking rule
    rule_line_number?: number // where it appears in output
    chain: string             // INPUT, FORWARD, etc.
    table: string             // filter, nat, etc.
    explanation: string       // why it blocks
    fix_command: string       // command to allow it
    fix_file_edit?: string    // file to edit if needed for persistence
}
