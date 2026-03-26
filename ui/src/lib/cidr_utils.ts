/**
 * IPv4 CIDR utilities convert IPs to numbers and check if an IP is in a range.
 *
 * Used for firewall rules, network diagrams, host sorting, etc.
 * No framework deps, can be used anywhere.
 */

// Parse "192.168.1.1" into a 32-bit number, or null if invalid
export function ip_to_number(ip: string): number | null {
    const parts = ip.split('.')
    if (parts.length !== 4) return null

    let result = 0
    for (const part of parts) {
        const num = parseInt(part, 10)
        if (isNaN(num) || num < 0 || num > 255) return null
        // Shift left 8 bits, add the next octet
        result = (result * 256 + num) >>> 0
    }
    return result
}

// Check if an IP is in a CIDR range. Plain IPs treated as /32.
// Returns false for bad input, so callers don't need special error handling.
export function ip_in_cidr(ip: string, cidr: string): boolean {
    // Split on "/" to extract network and prefix, default to /32 for plain IPs
    const slash_index = cidr.indexOf('/')
    const cidr_ip     = slash_index === -1 ? cidr : cidr.slice(0, slash_index)
    const prefix_str  = slash_index === -1 ? '32'  : cidr.slice(slash_index + 1)

    const prefix_length = parseInt(prefix_str, 10)
    if (isNaN(prefix_length) || prefix_length < 0 || prefix_length > 32) return false

    const ip_num   = ip_to_number(ip)
    const cidr_num = ip_to_number(cidr_ip)
    if (ip_num === null || cidr_num === null) return false

    // Mask off the network bits, compare both sides
    const mask = prefix_length === 0 ? 0 : (~0 << (32 - prefix_length)) >>> 0
    return (ip_num & mask) === (cidr_num & mask)
}
