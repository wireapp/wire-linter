/**
 * Checks whether the deeplink JSON configuration is complete.
 *
 * Consumes the config/deeplink_json target (boolean or string).
 * Needs these keys: backendURL, backendWSURL, teamsURL, accountsURL,
 * blackListURL, websiteURL, title. If any are missing, mobile clients
 * won't connect.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class DeeplinkJsonChecker extends BaseChecker {
    readonly path: string = 'helm_config/deeplink_json'
    readonly name: string = 'Deeplink JSON completeness'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that the deeplink JSON contains all required keys (`backendURL`, `backendWSURL`, `teamsURL`, `accountsURL`, `blackListURL`, `websiteURL`, `title`). Missing keys prevent **mobile clients from connecting**.'

    check(data: DataLookup): CheckResult {
        // Skip when deeplink is not configured for this deployment
        if (data.config && !data.config.options.expect_deeplink) {
            return {
                status: 'not_applicable',
                status_reason: 'Mobile deeplink is not enabled in the deployment settings - check skipped.',
                display_value: 'skipped',
                recommendation: 'Mobile deeplink is not enabled in the deployment settings - check skipped.',
            }
        }

        const point = data.get_applicable('config/deeplink_json') ?? data.get('direct/config/deeplink_json')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Deeplink JSON data was not collected.',
                fix_hint: '1. Verify the deeplink configuration exists:\n   ```\n   helm get values wire-server -n wire | grep -A10 deeplink\n   ```\n2. Re-run the gatherer ensuring the `config/deeplink_json` target succeeds.',
                recommendation: 'Couldn\'t collect deeplink JSON data.',
            }
        }

        // Null value means the gatherer failed to collect the data
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Deeplink JSON data was not collected.',
                recommendation: 'Couldn\'t collect deeplink JSON data.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value non-empty means deeplink JSON is complete
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'Deeplink JSON contains all required keys: `{{keys}}`.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { keys: val },
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'Deeplink JSON is **incomplete** — missing one or more required keys.',
                fix_hint: '1. Check the current deeplink configuration:\n   ```\n   helm get values wire-server -n wire | grep -A10 deeplink\n   ```\n2. Add the missing keys (`backendURL`, `backendWSURL`, `teamsURL`, `accountsURL`, `blackListURL`, `websiteURL`, `title`) to your helm values\n3. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
                recommendation: 'Deeplink JSON is incomplete. Missing one or more of: backendURL, backendWSURL, teamsURL, accountsURL, blackListURL, websiteURL, title. Mobile clients won\'t connect.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means all required keys are present
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Deeplink JSON contains all required keys.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false some keys are missing
        return {
            status: 'unhealthy',
            status_reason: 'Deeplink JSON is **incomplete** — missing one or more required keys.',
            fix_hint: '1. Check the current deeplink configuration:\n   ```\n   helm get values wire-server -n wire | grep -A10 deeplink\n   ```\n2. Add the missing keys (`backendURL`, `backendWSURL`, `teamsURL`, `accountsURL`, `blackListURL`, `websiteURL`, `title`) to your helm values\n3. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: 'Deeplink JSON incomplete. Required keys: backendURL, backendWSURL, teamsURL, accountsURL, blackListURL, websiteURL, title. Mobile clients refuse to connect if any key is missing.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default DeeplinkJsonChecker
