/**
 * Client-mode checker: TLS certificate validity for Wire subdomains.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientTlsValidityChecker extends BaseChecker {
    readonly path: string = 'client/tls_validity'
    readonly name: string = 'TLS certificates (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Checks TLS certificates for all Wire subdomains from this client network. Expired or invalid certificates cause connection failures in Wire clients.'

    check(data: DataLookup): CheckResult {
        const point = data.get('client/tls/certificate_validity')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Client TLS validity data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const all_valid: boolean = parsed.all_valid as boolean ?? false
        const results: Array<Record<string, unknown>> = (parsed.results as Array<Record<string, unknown>>) ?? []
        const invalid: Array<Record<string, unknown>> = results.filter(r => !(r.valid as boolean))

        if (all_valid) {
            return { status: 'healthy', status_reason: `All **${results.length}** TLS certificates are valid from this network.`, display_value: `${results.length}/${results.length} valid`, raw_output: point.raw_output }
        }

        const details: string = invalid.map(r => {
            const subdomain: string = (r.subdomain as string) ?? 'unknown'
            const error: string = (r.error as string) ?? 'invalid'
            return `\`${subdomain}\`: ${error}`
        }).join('\n- ')

        return {
            status: invalid.some(r => (r.error as string ?? '').includes('expired')) ? 'unhealthy' : 'warning',
            status_reason: `**${invalid.length}** certificate issue(s) from this network:\n- ${details}`,
            display_value: `${results.length - invalid.length}/${results.length} valid`,
            raw_output: point.raw_output,
        }
    }
}

export default ClientTlsValidityChecker
