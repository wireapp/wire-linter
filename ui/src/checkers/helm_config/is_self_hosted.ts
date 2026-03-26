/**
 * Checks whether the IS_SELF_HOSTED flag is set in team-settings and account-pages.
 *
 * Consumes the config/is_self_hosted target (boolean or string).
 * Without this flag, team-settings shows «wire for free» prompts and
 * payment UI that don't work in self-hosted setups.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class IsSelfHostedChecker extends BaseChecker {
    readonly path: string = 'helm_config/is_self_hosted'
    readonly name: string = 'IS_SELF_HOSTED flag set'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Checks that the `IS_SELF_HOSTED` flag is set in **team-settings** and **account-pages**. Without it, users see irrelevant "wire for free" prompts and non-functional payment UI.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/is_self_hosted')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: '`IS_SELF_HOSTED` flag data was not collected.',
                fix_hint: '1. Verify the team-settings and account-pages ConfigMaps exist:\n   ```\n   kubectl get configmap -n wire | grep -E "team-settings|account-pages"\n   ```\n2. Re-run the gatherer ensuring the `config/is_self_hosted` target succeeds.',
                recommendation: 'Couldn\'t collect IS_SELF_HOSTED flag data.',
            }
        }

        // Null value means the gatherer encountered an error collecting this target
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'IS_SELF_HOSTED flag data collection returned null (gatherer error).',
                recommendation: 'Couldn\'t collect IS_SELF_HOSTED flag data.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value non-empty means flag is set
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: '`IS_SELF_HOSTED` flag is set: `{{flag_value}}`.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { flag_value: val },
                }
            }

            return {
                status: 'unhealthy',
                status_reason: '`IS_SELF_HOSTED` flag is **not set** in team-settings and account-pages.',
                fix_hint: '1. Add `IS_SELF_HOSTED: "true"` to your team-settings and account-pages configuration in helm values\n2. Apply the change:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```\n3. Verify the flag is set:\n   ```\n   kubectl get configmap -n wire team-settings -o yaml | grep IS_SELF_HOSTED\n   ```',
                recommendation: 'IS_SELF_HOSTED flag not set in team-settings and account-pages. That means users see «wire for free» prompts and payment stuff that doesn\'t work on-prem.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means flag is set
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: '`IS_SELF_HOSTED` flag is set.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false flag not set
        return {
            status: 'unhealthy',
            status_reason: '`IS_SELF_HOSTED` flag is **not set** in team-settings and account-pages.',
            fix_hint: '1. Add `IS_SELF_HOSTED: "true"` to your team-settings and account-pages configuration in helm values\n2. Apply the change:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```\n3. Verify the flag is set:\n   ```\n   kubectl get configmap -n wire team-settings -o yaml | grep IS_SELF_HOSTED\n   ```',
            recommendation: 'IS_SELF_HOSTED flag not set in team-settings and account-pages. Without it, team-settings shows \'wire for free\' prompts and payment UI that doesn\'t work on-prem.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default IsSelfHostedChecker
