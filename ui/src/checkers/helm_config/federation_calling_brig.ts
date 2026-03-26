/**
 * Verifies brig's federation+calling settings (multiSFT, setSftListAllServers).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationCallingBrigChecker extends BaseChecker {
    readonly path: string = 'helm_config/federation_calling_brig'
    readonly name: string = 'Federation calling config (brig)'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Federated conference calls require `multiSFT.enabled: true` and `setSftListAllServers: "enabled"` in brig.'

    check(data: DataLookup): CheckResult {
        const opts = data.config?.options
        if (!opts?.expect_federation || !opts?.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Federation and/or calling not enabled.' }
        }

        const point = data.get('config/federation_calling_brig')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Federation calling brig config not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const multi_sft: boolean = parsed.multi_sft_enabled as boolean ?? false
        const sft_list_all: string = (parsed.sft_list_all_servers as string) ?? ''
        const issues: string[] = []

        if (!multi_sft) issues.push('`multiSFT.enabled` is false. SFT-to-SFT communication required for federated conference calls.')
        if (sft_list_all !== 'enabled') issues.push(`\`setSftListAllServers\` is \`${sft_list_all || 'not set'}\`. Must be \`enabled\` for federated calling.`)

        if (issues.length > 0) {
            return { status: 'unhealthy', status_reason: issues.join('\n\n'), display_value: `multiSFT: ${multi_sft}, listAll: ${sft_list_all || 'not set'}`, raw_output: point.raw_output }
        }

        return { status: 'healthy', status_reason: 'Brig federation calling settings correct: `multiSFT.enabled: true`, `setSftListAllServers: enabled`.', display_value: 'correctly configured', raw_output: point.raw_output }
    }
}

export default FederationCallingBrigChecker
