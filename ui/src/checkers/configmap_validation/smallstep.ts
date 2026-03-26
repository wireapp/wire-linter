/**
 * Checks if your Smallstep CA (MLS certificate authority) config is actually valid.
 *
 * Grabs the kubernetes/configmaps/smallstep target, parses the JSON, and looks
 * for embedded error messages that mean your provisioners are broken. If Smallstep
 * CA is broken, MLS end-to-end identity doesn't work.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class SmallstepConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/smallstep'
    readonly name: string = 'Smallstep CA configuration validity'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/smallstep'
    readonly explanation: string = 'Validates the **Smallstep CA** (MLS certificate authority) configuration for broken provisioners. If the CA is misconfigured, MLS **end-to-end identity** features will not function.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/configmaps/smallstep')

        // No data means we couldn't even gather it
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: '**Smallstep CA** ConfigMap data was not collected.',
                fix_hint: '1. Verify the Smallstep ConfigMap exists:\n   ```\n   kubectl get configmap -n wire | grep smallstep\n   ```\n2. Re-run the gatherer ensuring the `kubernetes/configmaps/smallstep` target succeeds.',
                recommendation: 'Smallstep CA ConfigMap data not collected.',
            }
        }

        const raw_json: string = String(point.value)

        // Empty ConfigMap means there's nothing to work with
        if (!raw_json.trim()) {
            return {
                status: 'unhealthy',
                status_reason: '**Smallstep CA** ConfigMap is **empty**.',
                fix_hint: '1. View the current Smallstep ConfigMap:\n   ```\n   kubectl get configmap -n wire smallstep-ca-config -o yaml\n   ```\n2. Redeploy Smallstep CA with correct configuration:\n   ```\n   helm upgrade smallstep wire/smallstep -f smallstep-values.yaml\n   ```',
                recommendation: 'Smallstep CA ConfigMap is empty. MLS end-to-end identity will not function.',
                raw_output: point.raw_output,
            }
        }

        // Try to parse the JSON, catch any parsing issues
        let parsed: unknown
        try {
            parsed = JSON.parse(raw_json)
        } catch (parse_error: unknown) {
            const message = parse_error instanceof Error ? parse_error.message : String(parse_error)
            return {
                status: 'unhealthy',
                status_reason: '**Smallstep CA** ConfigMap contains **invalid JSON**.',
                fix_hint: '1. View the current Smallstep ConfigMap:\n   ```\n   kubectl get configmap -n wire smallstep-ca-config -o yaml\n   ```\n2. Fix the JSON syntax error: `{{parse_message}}`\n3. Redeploy with corrected configuration:\n   ```\n   helm upgrade smallstep wire/smallstep -f smallstep-values.yaml\n   ```',
                recommendation: `Smallstep CA ConfigMap contains invalid JSON: ${message}`,
                raw_output: point.raw_output,
                configmap_data: raw_json,
                template_data: { parse_message: message },
            }
        }

        // Look for "Error" keys in the provisioners array, which means a
        // provisioner is broken and Smallstep couldn't parse it
        const errors: string[] = []
        const config = parsed as Record<string, unknown>

        const authority = config?.authority as Record<string, unknown> | undefined
        const provisioners = authority?.provisioners as Array<Record<string, unknown>> | undefined

        if (Array.isArray(provisioners)) {
            for (let i = 0; i < provisioners.length; i++) {
                const provisioner = provisioners[i]
                if (provisioner && typeof provisioner === 'object' && 'Error' in provisioner) {
                    errors.push(`Provisioner ${i}: ${String(provisioner.Error)}`)
                }
            }
        }

        if (errors.length > 0) {
            return {
                status: 'unhealthy',
                status_reason: '**Smallstep CA** has **{{error_count}}** broken provisioner(s).',
                fix_hint: '1. View the current Smallstep CA configuration:\n   ```\n   kubectl get configmap -n wire smallstep-ca-config -o yaml\n   ```\n2. Check the `authority.provisioners` array for entries with `Error` keys\n3. Fix or recreate the broken provisioners in your Smallstep configuration\n4. Redeploy:\n   ```\n   helm upgrade smallstep wire/smallstep -f smallstep-values.yaml\n   ```',
                recommendation: `Smallstep CA has ${errors.length} broken provisioner(s):\n${errors.join('\n')}\nMLS end-to-end identity features will not function until this is fixed.`,
                display_value: `${errors.length} error(s)`,
                raw_output: point.raw_output,
                configmap_data: raw_json,
                template_data: { error_count: errors.length },
            }
        }

        // Make sure the config has the basic structure it needs to work
        if (!authority || !provisioners || provisioners.length === 0) {
            return {
                status: 'warning',
                status_reason: 'Smallstep CA configuration is missing `authority` or `provisioners` section.',
                fix_hint: '1. View the current Smallstep CA configuration:\n   ```\n   kubectl get configmap -n wire smallstep-ca-config -o yaml\n   ```\n2. Ensure the configuration contains both an `authority` section and at least one entry in `authority.provisioners`\n3. Redeploy:\n   ```\n   helm upgrade smallstep wire/smallstep -f smallstep-values.yaml\n   ```',
                recommendation: 'Smallstep CA configuration is missing authority or provisioners.',
                raw_output: point.raw_output,
                configmap_data: raw_json,
            }
        }

        return {
            status: 'healthy',
            status_reason: '**Smallstep CA** configuration is valid with **{{provisioner_count}}** provisioner(s).',
            display_value: `${provisioners.length} provisioner(s)`,
            raw_output: point.raw_output,
            configmap_data: raw_json,
            template_data: { provisioner_count: provisioners.length },
        }
    }
}

export default SmallstepConfigmapChecker
