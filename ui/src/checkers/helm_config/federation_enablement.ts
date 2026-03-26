/**
 * Verifies enableFederation is consistent across brig, galley, cargohold, background-worker.
 *
 * When expect_federation is true: all 4 should be true.
 * When expect_federation is false: all 4 should be false (warn if any are randomly on).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationEnablementChecker extends BaseChecker {
    readonly path: string = 'helm_config/federation_enablement'
    readonly name: string = 'Federation enablement consistency'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Federation requires `enableFederation: true` in all four services (brig, galley, cargohold, background-worker). If any service is misconfigured, federation is partially broken.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/federation_enablement')

        if (!point?.value) {
            return {
                status: 'gather_failure',
                status_reason: 'Federation enablement data was not collected.',
            }
        }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) as Record<string, unknown> } catch { /* ignore */ }

        if (!parsed) {
            return {
                status: 'gather_failure',
                status_reason: 'Could not parse federation enablement data.',
                raw_output: point.raw_output,
            }
        }

        const expect_federation: boolean = data.config?.options?.expect_federation ?? false
        const all_enabled: boolean = parsed.all_enabled as boolean ?? false
        const all_disabled: boolean = parsed.all_disabled as boolean ?? false

        // Build per-service detail
        const services: string[] = ['brig', 'galley', 'cargohold', 'background-worker']
        const enabled_list: string[] = services.filter(s => parsed![s.replace('-', '_')] === true || parsed![s] === true)
        const disabled_list: string[] = services.filter(s => parsed![s.replace('-', '_')] === false || parsed![s] === false)

        if (expect_federation) {
            // Federation expected — all should be enabled
            if (all_enabled) {
                return {
                    status: 'healthy',
                    status_reason: 'Federation is enabled in all 4 services (brig, galley, cargohold, background-worker).',
                    display_value: 'all enabled',
                    raw_output: point.raw_output,
                }
            }

            const fix_lines: string[] = disabled_list.map(s =>
                `- Set \`${s}.config.enableFederation: true\` in helm values`
            )

            return {
                status: 'unhealthy',
                status_reason: `Federation is declared as enabled but these services have \`enableFederation: false\`: **${disabled_list.join(', ')}**.`,
                fix_hint: fix_lines.join('\n') + '\n\nThen redeploy:\n```\nhelm upgrade wire-server wire/wire-server -f values.yaml\n```',
                recommendation: `Enable federation in: ${disabled_list.join(', ')}`,
                display_value: `${enabled_list.length}/4 enabled`,
                raw_output: point.raw_output,
            }
        }

        // Federation not expected
        if (all_disabled) {
            return {
                status: 'healthy',
                status_reason: 'Federation is disabled in all services (consistent with deployment configuration).',
                display_value: 'all disabled',
                raw_output: point.raw_output,
            }
        }

        // Some services have federation enabled but it's not declared
        return {
            status: 'warning',
            status_reason: `Federation is not declared as enabled, but these services have \`enableFederation: true\`: **${enabled_list.join(', ')}**. This may cause unexpected behavior.`,
            recommendation: `Either enable federation in the deployment configuration, or disable it in: ${enabled_list.join(', ')}`,
            display_value: `${enabled_list.length}/4 unexpectedly enabled`,
            raw_output: point.raw_output,
        }
    }
}

export default FederationEnablementChecker
