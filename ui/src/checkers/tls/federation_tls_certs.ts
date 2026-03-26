/**
 * Checks federation TLS certificates: client cert existence, expiry, SANs; CA certs.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationTlsCertsChecker extends BaseChecker {
    readonly path: string = 'tls/federation_tls_certs'
    readonly name: string = 'Federation TLS certificates'
    readonly category: string = 'TLS / Certificates'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Federation uses mutual TLS. The federator needs a client certificate with the infrastructure domain as SAN, and CA certificates to verify partners.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_federation) {
            return { status: 'not_applicable', status_reason: 'Federation is not enabled.' }
        }

        const point = data.get('tls/federation_certificates')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Federation TLS cert data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const client_found: boolean = parsed.client_cert_found as boolean ?? false
        const ca_found: boolean = parsed.ca_certs_found as boolean ?? false
        const days: number = (parsed.client_cert_days_remaining as number) ?? -1
        const issues: string[] = []

        if (!client_found) issues.push('Federator **client certificate not found**. Federation authentication will fail.')
        else if (days >= 0 && days < 7) issues.push(`Federator client certificate **expires in ${days} days**. Renew immediately.`)
        else if (days >= 0 && days < 30) issues.push(`Federator client certificate expires in ${days} days. Plan renewal.`)

        if (!ca_found) issues.push('No federation **CA certificates** found. Cannot verify federation partners.')

        if (issues.length > 0) {
            const has_critical: boolean = !client_found || days < 7
            return { status: has_critical ? 'unhealthy' : 'warning', status_reason: issues.join('\n\n'), raw_output: point.raw_output }
        }

        return { status: 'healthy', status_reason: `Federation TLS: client cert found${days >= 0 ? ` (${days} days remaining)` : ''}, CA certs present.`, raw_output: point.raw_output }
    }
}

export default FederationTlsCertsChecker
