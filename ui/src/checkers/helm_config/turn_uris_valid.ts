/**
 * Validates TURN URI format and count for high availability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class TurnUrisValidChecker extends BaseChecker {
    readonly path: string = 'helm_config/turn_uris_valid'
    readonly name: string = 'TURN URI format and HA'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies TURN server URIs are correctly formatted and that at least two servers are configured for high availability.'

    check(data: DataLookup): CheckResult {
        if (data.config && (!data.config.options.expect_calling || data.config.options.calling_type !== 'on_prem')) {
            return { status: 'not_applicable', status_reason: 'On-prem calling is not enabled.' }
        }

        const point = data.get('config/brig_calling_config')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Calling config not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse calling config.' }

        const uris: string[] = (parsed.turn_v2_uris as string[]) ?? []
        if (uris.length === 0) return { status: 'not_applicable', status_reason: 'No TURN URIs configured.' }

        // Extract unique hosts from URIs (turn:<host>:<port>)
        const hosts: Set<string> = new Set()
        const has_tcp: boolean = uris.some(u => u.includes('transport=tcp'))

        for (const uri of uris) {
            const match = uri.match(/^turns?:([^:?]+)/)
            if (match && match[1]) hosts.add(match[1])
        }

        const warnings: string[] = []
        if (hosts.size < 2) warnings.push('Only one unique TURN server. Wire recommends at least two for high availability.')
        if (!has_tcp) warnings.push('No TCP transport TURN URIs. Adding TCP variants improves connectivity for clients behind restrictive firewalls.')

        if (warnings.length > 0) {
            return { status: 'warning', status_reason: warnings.join('\n\n'), display_value: `${uris.length} URI(s), ${hosts.size} server(s)`, raw_output: point.raw_output }
        }

        return { status: 'healthy', status_reason: `**${uris.length}** TURN URI(s) across **${hosts.size}** server(s), including TCP variants.`, display_value: `${uris.length} URI(s), ${hosts.size} server(s)`, raw_output: point.raw_output }
    }
}

export default TurnUrisValidChecker
