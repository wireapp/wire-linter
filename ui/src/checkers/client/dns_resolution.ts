/**
 * Client-mode checker: DNS resolution of Wire subdomains.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientDnsResolutionChecker extends BaseChecker {
    readonly path: string = 'client/dns_resolution'
    readonly name: string = 'DNS resolution (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies that all required Wire subdomains resolve from this client network. If any fail, clients on this network cannot reach those services.'

    check(data: DataLookup): CheckResult {
        const point = data.get('client/dns/subdomain_resolution')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Client DNS resolution data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const all_resolved: boolean = parsed.all_resolved as boolean ?? false
        const results: Array<Record<string, unknown>> = (parsed.results as Array<Record<string, unknown>>) ?? []
        const failed: string[] = results.filter(r => !(r.resolved as boolean)).map(r => `\`${r.subdomain}\``)

        if (all_resolved) {
            return { status: 'healthy', status_reason: `All **${results.length}** Wire subdomains resolve from this network.`, display_value: `${results.length}/${results.length} resolved`, raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: `**${failed.length}** subdomain(s) failed to resolve: ${failed.join(', ')}. Wire clients on this network cannot reach these services.`,
            fix_hint: 'Verify DNS records exist for all Wire subdomains. Check with:\n```\ndig <subdomain>\n```',
            display_value: `${results.length - failed.length}/${results.length} resolved`,
            raw_output: point.raw_output,
        }
    }
}

export default ClientDnsResolutionChecker
