/**
 * Verifies legal hold configuration: galley feature flag, pods, secrets.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class LegalholdConfigurationChecker extends BaseChecker {
    readonly path: string = 'helm_config/legalhold_configuration'
    readonly name: string = 'Legal hold configuration'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Legal hold requires galley\'s legalhold feature flag to be `disabled-by-default` (not `disabled-permanently`), the legalhold service running, and secrets configured.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_legalhold) {
            return { status: 'not_applicable', status_reason: 'Legal hold is not enabled in the deployment configuration.' }
        }

        const flag_point = data.get('config/galley_legalhold_flag')
        if (!flag_point?.value) return { status: 'gather_failure', status_reason: 'Galley legalhold flag not collected.' }

        const flag: string = String(flag_point.value).trim()
        const issues: string[] = []

        if (flag === 'disabled-permanently' || flag === 'not set') {
            issues.push(`Galley legalhold flag is \`${flag}\`. Must be \`disabled-by-default\` for legal hold to be activatable per-team.`)
        }

        // Check pods
        const pod_point = data.get('wire_services/legalhold_healthy')
        if (pod_point && pod_point.value === false) {
            issues.push('Legalhold pods are not running. The service may run outside Kubernetes as a Docker container.')
        }

        if (issues.length > 0) {
            return {
                status: (issues[0] ?? '').includes('disabled-permanently') ? 'unhealthy' : 'warning',
                status_reason: issues.join('\n\n'),
                fix_hint: 'Set galley legalhold flag:\n```yaml\ngalley:\n  config:\n    settings:\n      featureFlags:\n        legalhold: disabled-by-default\n```',
                display_value: flag,
                raw_output: flag_point.raw_output,
            }
        }

        return { status: 'healthy', status_reason: `Legal hold flag: \`${flag}\`. Legal hold can be activated per-team.`, display_value: flag, raw_output: flag_point.raw_output }
    }
}

export default LegalholdConfigurationChecker
