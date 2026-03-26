/**
 * Validates federation strategy and domain configs in brig.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationStrategyChecker extends BaseChecker {
    readonly path: string = 'helm_config/federation_strategy'
    readonly name: string = 'Federation strategy'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Federation strategy (`allowNone`/`allowAll`/`allowDynamic`) controls which backends are allowed to federate. `allowNone` effectively disables federation even when `enableFederation` is true.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_federation) {
            return { status: 'not_applicable', status_reason: 'Federation is not enabled.' }
        }

        const point = data.get('config/federation_strategy')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Federation strategy data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse federation strategy data.' }

        const strategy: string = (parsed.strategy as string) ?? 'allowNone'
        const domain_configs: Array<Record<string, string>> = (parsed.domain_configs as Array<Record<string, string>>) ?? []
        const declared_domains: string[] = data.config?.options?.federation_domains ?? []

        if (strategy === 'allowNone') {
            return {
                status: 'unhealthy',
                status_reason: 'Federation strategy is `allowNone` — federation is effectively **disabled** even though `enableFederation` is true.',
                fix_hint: 'Set the strategy in brig helm values:\n```yaml\nbrig:\n  config:\n    optSettings:\n      setFederationStrategy: allowDynamic\n```',
                display_value: 'allowNone (disabled)',
                raw_output: point.raw_output,
            }
        }

        if (strategy === 'allowDynamic') {
            // Check that declared domains are in the config
            const configured_domains: string[] = domain_configs.map(c => c.domain ?? '')
            const missing: string[] = declared_domains.filter(d => d && !configured_domains.includes(d))

            if (missing.length > 0) {
                return {
                    status: 'unhealthy',
                    status_reason: `Strategy is \`allowDynamic\` but these declared federation partners are missing from \`setFederationDomainConfigs\`: **${missing.join(', ')}**.`,
                    fix_hint: missing.map(d => `Add to brig optSettings.setFederationDomainConfigs:\n  - domain: ${d}\n    search_policy: full_search`).join('\n'),
                    display_value: `allowDynamic (${missing.length} missing)`,
                    raw_output: point.raw_output,
                }
            }
        }

        return {
            status: 'healthy',
            status_reason: `Federation strategy: \`${strategy}\`${domain_configs.length > 0 ? `, ${domain_configs.length} domain(s) configured` : ''}.`,
            display_value: strategy,
            raw_output: point.raw_output,
        }
    }
}

export default FederationStrategyChecker
