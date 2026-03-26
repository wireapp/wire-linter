/**
 * Verifies coturn federation settings (federate.enabled, DTLS port).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationCallingCoturnChecker extends BaseChecker {
    readonly path: string = 'helm_config/federation_calling_coturn'
    readonly name: string = 'Federation calling config (coturn)'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Coturn must have `federate.enabled: true` for federated calling, with a dedicated federation port (typically 9191).'

    check(data: DataLookup): CheckResult {
        const opts = data.config?.options
        if (!opts?.expect_federation || !opts?.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Federation and/or calling not enabled.' }
        }

        const point = data.get('config/federation_calling_coturn')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Coturn federation config not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        if (!(parsed.found_in_cluster as boolean)) {
            if (opts.calling_in_dmz) return { status: 'not_applicable', status_reason: 'Coturn in separate DMZ cluster.' }
            return { status: 'warning', status_reason: 'Coturn not found in cluster.' }
        }

        if (!(parsed.federate_enabled as boolean)) {
            return { status: 'unhealthy', status_reason: 'Coturn `federate.enabled` is false. Set to true for federated calling.', raw_output: point.raw_output }
        }

        return { status: 'healthy', status_reason: `Coturn federation enabled${(parsed.federate_port as number) ? `, port ${parsed.federate_port}` : ''}.`, raw_output: point.raw_output }
    }
}

export default FederationCallingCoturnChecker
