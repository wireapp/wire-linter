/**
 * Checks if the federation domain is set the same way in both brig and galley.
 *
 * The config/federation_domain target gives us back a boolean or string. When both
 * services have no federation domain configured, the target returns 'not_configured'
 * which is normal for non-federation deployments. When configured, both services
 * must have the exact same value.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class DomainConsistencyChecker extends BaseChecker {
    readonly path: string = 'federation/domain_consistency'
    readonly name: string = 'Federation domain set consistently in brig and galley'
    readonly category: string = 'Federation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that brig and galley have the same federation domain configured. When federation is not used, both values being absent is normal. A mismatch or partially-set value indicates misconfiguration.'

    check(data: DataLookup): CheckResult {
        // Skip when federation is not expected
        if (data.config && !data.config.options.expect_federation) {
            return { status: 'not_applicable', status_reason: 'Federation is not enabled in the deployment configuration.' }
        }

        const point = data.get('config/federation_domain')

        // Data didn't come back from the target
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Federation domain consistency data was not collected.',
                fix_hint: '1. Re-run the gatherer with the `federation_domain` target enabled\n2. Verify the gatherer has access to both brig and galley ConfigMaps:\n   - `kubectl get configmap brig -o yaml`\n   - `kubectl get configmap galley -o yaml`\n3. Check gatherer logs for errors accessing Kubernetes resources',
                recommendation: 'Federation domain set consistently in brig and galley data not collected.',
            }
        }

        // Null value means the gatherer encountered an error collecting this target
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Federation domain consistency data collection returned null (gatherer error).',
                recommendation: 'Federation domain set consistently in brig and galley data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // Include the expected domain when available so the recommendation is actionable
        const expected: string = data.config?.cluster.domain ?? ''
        const domain_hint: string = expected
            ? ` Both should be set to «${expected}».`
            : ''
        const fail_recommendation: string = `Federation domain isn't set the same way in both services. When configured, brig and galley must have matching values.${domain_hint}`

        // Neither service has a federation domain — normal for non-federation deployments
        if (val === 'not_configured') {
            return {
                status: 'not_applicable',
                status_reason: 'Federation domain is not configured in either brig or galley. This is expected for non-federation deployments.',
                display_value: 'Not configured',
                raw_output: point.raw_output,
            }
        }

        // If we get a string, validate it looks like a real domain before treating it as healthy.
        // Error strings from the gatherer (e.g. "error: config not found") would otherwise
        // produce a false-positive healthy result.
        if (typeof val === 'string') {
            const domain_pattern = /^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/

            if (domain_pattern.test(val)) {
                return {
                    status: 'healthy',
                    status_reason: 'Federation domain is set consistently in both **brig** and **galley** (`{{domain_value}}`).',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { domain_value: val },
                }
            }

            // Empty string or anything that doesn't look like a domain (including error strings)
            return {
                status: val.length === 0 ? 'unhealthy' : 'gather_failure',
                status_reason: val.length === 0
                    ? 'Federation domain value is empty, meaning it is not configured in brig and/or galley.'
                    : `Federation domain value does not look like a valid domain: "${val}".`,
                recommendation: val.length === 0 ? fail_recommendation : undefined,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { expected },
            }
        }

        // Boolean true everything's consistent
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Federation domain is set consistently in both **brig** and **galley**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false inconsistent or it's missing
        return {
            status: 'unhealthy',
            status_reason: 'Federation domain is either **missing** or **inconsistent** between brig and galley.',
            fix_hint: '1. Check brig federation domain: `kubectl get configmap brig -o yaml | grep -i federation`\n2. Check galley federation domain: `kubectl get configmap galley -o yaml | grep -i federation`\n3. Compare the values \u2014 they must be identical\n4. Set both in Helm values:\n   - `brig.config.optSettings.setFederationDomain`\n   - `galley.config.settings.federationDomain`\n{{#if expected}}5. Both must be set to `{{expected}}`\n{{/if}}6. Apply: `helm upgrade wire-server wire/wire-server -f values.yaml`',
            recommendation: fail_recommendation,
            display_value: val,
            raw_output: point.raw_output,
            template_data: { expected },
        }
    }
}

export default DomainConsistencyChecker
