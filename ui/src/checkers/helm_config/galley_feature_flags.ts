/**
 * Checks whether all required Galley feature flags are present.
 *
 * Consumes the config/galley_feature_flags target (boolean or string).
 * Needs: sso, legalhold, teamSearchVisibility, mls, mlsMigration.
 * If any flag is missing, Galley goes into CrashLoopBackOff.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class GalleyFeatureFlagsChecker extends BaseChecker {
    readonly path: string = 'helm_config/galley_feature_flags'
    readonly name: string = 'Galley feature flags completeness'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Ensures all required Galley feature flags (`sso`, `legalhold`, `teamSearchVisibility`, `mls`, `mlsMigration`) are present. A missing flag causes Galley to enter **CrashLoopBackOff**.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/galley_feature_flags')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Galley feature flags data was not collected.',
                fix_hint: '1. Verify the Galley ConfigMap exists:\n   ```\n   kubectl get configmap galley -n wire -o yaml\n   ```\n2. Re-run the gatherer ensuring the `config/galley_feature_flags` target succeeds.',
                recommendation: 'Couldn\'t collect Galley feature flags data.',
            }
        }

        // If the gatherer hit an error, report it instead of misinterpreting the value
        const collection_error: string | undefined = point.metadata?.error
        if (collection_error) {
            return {
                status: 'gather_failure',
                status_reason: `Galley feature flags could not be checked: ${collection_error}`,
                recommendation: `Galley feature flags could not be checked: ${collection_error}`,
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean
        const required_flags: string[] = ['sso', 'legalhold', 'teamSearchVisibility', 'mls', 'mlsMigration']

        // String value: validate that all required flag names actually appear
        if (typeof val === 'string') {
            if (val.length === 0) {
                return {
                    status: 'warning',
                    status_reason: 'Feature flags data was empty — cannot determine completeness.',
                    recommendation: 'The gathered feature flags string was empty. This may mean the configmap was empty, the feature flags section did not exist, or the gatherer could not parse the config. Verify the Galley configmap manually.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Split on commas and whitespace to build a set of exact flag names,
            // preventing substring false positives (e.g. 'mls' matching inside 'mlsMigration')
            const present_flags: Set<string> = new Set(val.split(/[\s,]+/).filter(s => s.length > 0))
            const missing_flags: string[] = required_flags.filter(flag => !present_flags.has(flag))

            if (missing_flags.length === 0) {
                return {
                    status: 'healthy',
                    status_reason: 'All required Galley feature flags are present: `{{flags}}`.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { flags: val },
                }
            }

            return {
                status: 'unhealthy',
                status_reason: `Galley feature flags are incomplete — missing: ${missing_flags.join(', ')}.`,
                recommendation: `Missing Galley feature flags: ${missing_flags.join(', ')}. All of ${required_flags.join(', ')} are required; a missing flag causes CrashLoopBackOff.`,
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means all flags are present
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All required Galley feature flags are present.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false some flags are missing
        return {
            status: 'unhealthy',
            status_reason: 'Galley feature flags are **incomplete** — missing one or more required flags.',
            fix_hint: '1. Check the current Galley feature flags:\n   ```\n   helm get values wire-server -n wire | grep -A20 featureFlags\n   ```\n2. Add the missing flags (`sso`, `legalhold`, `teamSearchVisibility`, `mls`, `mlsMigration`) to your helm values\n3. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: 'Galley feature flags incomplete. Required: sso, legalhold, teamSearchVisibility, mls, mlsMigration. One missing key causes CrashLoopBackOff.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default GalleyFeatureFlagsChecker
