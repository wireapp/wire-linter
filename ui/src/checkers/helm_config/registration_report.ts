/**
 * Reports the auto-detected user registration / account creation settings.
 *
 * Reads brig registration config and webapp registration config to report
 * how user accounts are created. Flags inconsistencies between backend
 * settings and webapp UI (e.g. backend blocks registration but webapp
 * still shows the registration form).
 */

// External
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class RegistrationReportChecker extends BaseChecker {
    readonly path: string = 'helm_config/registration_report'
    readonly name: string = 'User registration configuration'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports how user accounts are created on this deployment: open registration, domain-restricted, or disabled. Also checks consistency between brig (backend) and webapp (UI) settings.'

    check(data: DataLookup): CheckResult {
        const brig_point = data.get('config/brig_registration_config')
        const webapp_point = data.get('config/webapp_registration_config')

        if (!brig_point?.value) {
            return {
                status: 'gather_failure',
                status_reason: 'Brig registration config data was not collected.',
            }
        }

        let brig_data: Record<string, unknown> | null = null
        try { brig_data = JSON.parse(String(brig_point.value)) as Record<string, unknown> } catch { /* ignore */ }
        if (!brig_data) {
            return {
                status: 'gather_failure',
                status_reason: 'Could not parse brig registration config.',
                raw_output: brig_point.raw_output,
            }
        }

        const restrict: boolean = brig_data.restrict_user_creation as boolean ?? false
        const domains: string[] = (brig_data.allowlist_email_domains as string[]) ?? []
        const has_domain_restriction: boolean = domains.length > 0

        // Parse webapp config if available
        let webapp_registration_shown: boolean | null = null
        if (webapp_point?.value) {
            let webapp_data: Record<string, unknown> | null = null
                try { webapp_data = JSON.parse(String(webapp_point.value)) as Record<string, unknown> } catch { /* ignore */ }
            if (webapp_data) {
                webapp_registration_shown = webapp_data.account_registration_enabled as boolean ?? null
            }
        }

        // Determine mode and build report
        let mode: string
        let details: string

        if (restrict) {
            mode = 'restricted'
            details = 'Public registration is **disabled** (`setRestrictUserCreation: true`). Users can only be created via team invitations, SSO, SCIM, or the internal API.'
        } else if (has_domain_restriction) {
            mode = 'domain-restricted'
            details = `Registration is restricted to email domains: **${domains.join(', ')}**.`
        } else {
            mode = 'open'
            details = 'Public registration is **open** — anyone can create an account.'
        }

        // Check brig vs webapp consistency
        let inconsistency: string = ''
        if (restrict && webapp_registration_shown === true) {
            inconsistency = '\n\n**Inconsistency:** The backend blocks registration (`setRestrictUserCreation: true`) but the webapp still shows the registration form (`FEATURE_ENABLE_ACCOUNT_REGISTRATION: true`). Users will see the form but registration will fail. Set `FEATURE_ENABLE_ACCOUNT_REGISTRATION` to `"false"` in webapp helm values.'
        } else if (!restrict && webapp_registration_shown === false) {
            inconsistency = '\n\n**Note:** The backend allows registration but the webapp hides the registration form. Users can still register via the API but not through the webapp UI.'
        }

        const has_warning: boolean = inconsistency.length > 0

        return {
            status: has_warning ? 'warning' : 'healthy',
            status_reason: `${details}${inconsistency}`,
            display_value: mode,
            raw_output: brig_point.raw_output,
        }
    }
}

export default RegistrationReportChecker
