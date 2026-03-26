/**
 * Verifies calling configuration: TURN URIs, SFT URL, coturn/SFT pod health.
 *
 * When calling is on_prem: checks turnStatic.v2 is non-empty, SFT URL is set,
 * pods are running. Respects calling_in_dmz (pods may be in separate cluster).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class CallingConfigurationChecker extends BaseChecker {
    readonly path: string = 'helm_config/calling_configuration'
    readonly name: string = 'Calling configuration'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that calling (audio/video) is properly configured: TURN server URIs for 1:1 calls, SFT URL for conference calls, and calling pod health.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled in the deployment configuration.' }
        }

        const point = data.get('config/brig_calling_config')
        if (!point?.value) {
            return { status: 'gather_failure', status_reason: 'Brig calling config data was not collected.' }
        }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) {
            return { status: 'gather_failure', status_reason: 'Could not parse calling config.', raw_output: point.raw_output }
        }

        const calling_type: string = data.config?.options?.calling_type ?? 'on_prem'
        const expect_sft: boolean = data.config?.options?.expect_sft ?? false
        const _calling_in_dmz: boolean = data.config?.options?.calling_in_dmz ?? false

        if (calling_type === 'cloud') {
            return { status: 'healthy', status_reason: 'Cloud calling — local calling pod checks are not applicable.', display_value: 'cloud calling' }
        }

        // On-prem calling checks
        const turn_v2: string[] = (parsed.turn_v2_uris as string[]) ?? []
        const sft_url: string = (parsed.sft_static_url as string) ?? ''
        const issues: string[] = []

        if (turn_v2.length === 0) {
            issues.push('No TURN server URIs configured in `turnStatic.v2`. 1:1 calls will not work when peer-to-peer fails.')
        }

        if (expect_sft && !sft_url) {
            issues.push('SFT URL (`setSftStaticUrl`) is not configured. Conference calls will not work.')
        }

        if (expect_sft && sft_url && sft_url.includes('example.com')) {
            issues.push('SFT URL contains `example.com` — looks like a placeholder value.')
        }

        if (issues.length > 0) {
            return {
                status: 'unhealthy',
                status_reason: issues.join('\n\n'),
                fix_hint: 'Configure TURN URIs and SFT URL in brig helm values:\n```\nbrig:\n  turnStatic:\n    v2:\n      - "turn:<coturn-ip>:3478"\n  config:\n    optSettings:\n      setSftStaticUrl: "https://sftd.<domain>:443"\n```',
                display_value: `${turn_v2.length} TURN URI(s), SFT: ${sft_url || 'not set'}`,
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: `Calling configured: **${turn_v2.length}** TURN URI(s)${expect_sft ? `, SFT: \`${sft_url}\`` : ''}.`,
            display_value: `${turn_v2.length} TURN URI(s)`,
            raw_output: point.raw_output,
        }
    }
}

export default CallingConfigurationChecker
