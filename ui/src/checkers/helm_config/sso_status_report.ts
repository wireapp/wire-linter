/**
 * Reports the auto-detected SSO (SAML) status.
 *
 * Reads the galley SSO feature flag and spar configuration to determine if
 * SSO is enabled. This is auto-detected, not a user question.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class SsoStatusReportChecker extends BaseChecker {
    readonly path: string = 'helm_config/sso_status_report'
    readonly name: string = 'SSO (SAML) status'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports whether SAML SSO authentication is enabled. SSO requires the galley `sso` feature flag set to `enabled-by-default` and the spar service running with at least one Identity Provider configured.'

    check(data: DataLookup): CheckResult {
        const sso_flag_point = data.get('config/galley_sso_flag')

        if (!sso_flag_point?.value) {
            return {
                status: 'gather_failure',
                status_reason: 'Galley SSO flag data was not collected.',
            }
        }

        const sso_flag: string = String(sso_flag_point.value).trim()
        const is_enabled: boolean = sso_flag.toLowerCase().includes('enabled')

        // Check spar health
        const spar_health = data.get('wire_services/spar/healthy')
        const spar_healthy: boolean = spar_health?.value === true || spar_health?.value === 'true'

        // Check IdP count (from existing cassandra target)
        const idp_point = data.get('cassandra/spar_idp_count')
        let idp_count: number = -1
        if (idp_point?.value !== undefined) {
            const parsed_count: number = Number(idp_point.value)
            if (!isNaN(parsed_count)) idp_count = parsed_count
        }

        if (!is_enabled) {
            return {
                status: 'healthy',
                status_reason: `SSO is **disabled** (galley flag: \`${sso_flag}\`). SAML authentication is not available.`,
                display_value: `disabled (${sso_flag})`,
                raw_output: sso_flag_point.raw_output,
            }
        }

        // SSO is enabled — check that the supporting infrastructure is healthy
        const issues: string[] = []

        if (!spar_healthy) {
            issues.push('spar service is not healthy')
        }

        if (idp_count === 0) {
            issues.push('no SAML Identity Providers are registered')
        }

        if (issues.length > 0) {
            return {
                status: 'warning',
                status_reason: `SSO is **enabled** (galley flag: \`${sso_flag}\`) but: ${issues.join('; ')}. Users cannot log in via SSO until these are resolved.`,
                display_value: `enabled (${issues.length} issue(s))`,
                raw_output: sso_flag_point.raw_output,
            }
        }

        const idp_info: string = idp_count >= 0 ? `, ${idp_count} IdP(s) configured` : ''

        return {
            status: 'healthy',
            status_reason: `SSO is **enabled** (galley flag: \`${sso_flag}\`). Spar is healthy${idp_info}.`,
            display_value: `enabled${idp_info}`,
            raw_output: sso_flag_point.raw_output,
        }
    }
}

export default SsoStatusReportChecker
