/**
 * Checks DNS SRV records for federation partner domains.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationSrvRecordsChecker extends BaseChecker {
    readonly path: string = 'dns/federation_srv_records'
    readonly name: string = 'Federation DNS SRV records'
    readonly category: string = 'DNS'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Federation discovery uses DNS SRV records (`_wire-server-federator._tcp.<domain>`) to find each partner\'s federator endpoint.'

    check(data: DataLookup): CheckResult {
        const opts = data.config?.options
        if (!opts?.expect_federation) return { status: 'not_applicable', status_reason: 'Federation not enabled.' }

        const domains: string[] = opts.federation_domains ?? []
        if (domains.length === 0) return { status: 'not_applicable', status_reason: 'No federation partner domains declared.' }

        const point = data.get('dns/federation_srv_records')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Federation SRV record data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const results: Array<Record<string, unknown>> = (parsed.results as Array<Record<string, unknown>>) ?? []
        const resolved: number = results.filter(r => r.srv_found as boolean).length
        const failed: string[] = results.filter(r => !(r.srv_found as boolean)).map(r => String(r.domain))

        if (failed.length > 0) {
            return {
                status: 'unhealthy',
                status_reason: `**${failed.length}** federation partner(s) missing SRV records: ${failed.map(d => `\`${d}\``).join(', ')}. Federation discovery will fail for these partners.`,
                fix_hint: failed.map(d => `Partner \`${d}\` must publish:\n\`_wire-server-federator._tcp.${d}. 600 IN SRV 10 5 443 federator.${d}.\``).join('\n\n'),
                display_value: `${resolved}/${results.length} resolved`,
                raw_output: point.raw_output,
            }
        }

        return { status: 'healthy', status_reason: `All **${resolved}** federation partner SRV records resolved.`, display_value: `${resolved}/${results.length} resolved`, raw_output: point.raw_output }
    }
}

export default FederationSrvRecordsChecker
