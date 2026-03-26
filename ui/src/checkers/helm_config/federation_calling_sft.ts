/**
 * Verifies SFT federation calling settings (multiSFT in the SFT chart).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationCallingSftChecker extends BaseChecker {
    readonly path: string = 'helm_config/federation_calling_sft'
    readonly name: string = 'Federation calling config (SFT)'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'The SFT chart must have `multiSFT.enabled: true`, a `turnServerURI`, and a shared `secret` for federated conference calls.'

    check(data: DataLookup): CheckResult {
        const opts = data.config?.options
        if (!opts?.expect_federation || !opts?.expect_calling || !opts?.expect_sft) {
            return { status: 'not_applicable', status_reason: 'Federation + calling + SFT not all enabled.' }
        }

        const point = data.get('config/federation_calling_sft')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'SFT federation config not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        if (!(parsed.found_in_cluster as boolean)) {
            if (opts.calling_in_dmz) return { status: 'not_applicable', status_reason: 'SFT in separate DMZ cluster.' }
            return { status: 'warning', status_reason: 'SFT not found in cluster.' }
        }

        const issues: string[] = []
        if (!(parsed.multi_sft_enabled as boolean)) issues.push('SFT `multiSFT.enabled` is false.')
        if (!(parsed.turn_server_uri as string)) issues.push('SFT `multiSFT.turnServerURI` is not set.')
        if (!(parsed.secret_configured as boolean)) issues.push('SFT `multiSFT.secret` is not configured.')

        if (issues.length > 0) {
            return { status: 'unhealthy', status_reason: issues.join('\n\n'), raw_output: point.raw_output }
        }

        return { status: 'healthy', status_reason: 'SFT federation calling correctly configured.', raw_output: point.raw_output }
    }
}

export default FederationCallingSftChecker
