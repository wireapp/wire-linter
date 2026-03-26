/**
 * Makes sure brig's federation domain setting matches what the cluster actually is.
 *
 * If these don't match brig's optSettings.setFederationDomain is pointing at the
 * wrong domain then federation API calls will fail and cross-team @mentions break.
 * This usually happens after migrating domains or just copy-paste mistakes. We're
 * looking at config/brig_federation_domain, which returns a boolean (WPB-17553).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class BrigFederationDomainChecker extends BaseChecker {
    readonly path: string = 'federation/brig_domain_matches_cluster'
    readonly name: string = 'Brig federation domain matches cluster (see: WPB-17553)'
    readonly category: string = 'Federation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that brig\'s `optSettings.setFederationDomain` matches the actual **cluster domain**. A mismatch causes federation API calls to fail and breaks cross-team @mentions, typically after a domain migration or a copy-paste error in Helm values.'

    check(data: DataLookup): CheckResult {
        // Skip when federation is not expected
        if (data.config && !data.config.options.expect_federation) {
            return { status: 'not_applicable', status_reason: 'Federation is not enabled in the deployment configuration.' }
        }

        const point = data.get('config/brig_federation_domain')

        // If we didn't get data from the target, we can't check anything
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Brig federation domain comparison data was not collected.',
                fix_hint: '1. Re-run the gatherer with the `brig_federation_domain` target enabled\n2. Verify the gatherer has access to the brig ConfigMap: `kubectl get configmap brig -o yaml`\n3. Check gatherer logs for errors accessing Kubernetes resources',
                recommendation: 'Brig federation domain vs cluster domain data not collected.',
            }
        }

        const val = point.value as boolean | string

        // True means they match, we're good
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Brig\'s `optSettings.setFederationDomain` matches the cluster domain.',
                display_value: 'domain matches',
                raw_output: point.raw_output,
            }
        }

        // False means they don't match that's a problem
        if (val === false) {
            // Include the expected domain from config when available so the
            // operator knows exactly what value to set in brig's Helm values
            const expected: string = data.config?.cluster.domain ?? ''

            return {
                status: 'unhealthy',
                status_reason: 'Brig\'s `optSettings.setFederationDomain` does **not** match the cluster domain{{#if expected}} (`{{expected}}`){{/if}}.',
                fix_hint: '1. Check the current brig federation domain: `kubectl get configmap brig -o yaml | grep setFederationDomain`\n2. Compare with the cluster domain{{#if expected}}: expected value is `{{expected}}`{{/if}}\n3. Update brig Helm values: set `brig.config.optSettings.setFederationDomain` to match the cluster domain\n4. Apply the change: `helm upgrade wire-server wire/wire-server -f values.yaml`\n5. Verify after deploy: `kubectl get configmap brig -o yaml | grep setFederationDomain`',
                recommendation: `Brig's optSettings.setFederationDomain doesn't match the cluster domain. This breaks federation API calls and cross-team @mentions.${expected ? ` The cluster domain is «${expected}» - set optSettings.setFederationDomain to match.` : ''}`,
                display_value: 'domain mismatch',
                raw_output: point.raw_output,
                template_data: { expected },
            }
        }

        // If we get a string instead of a boolean, that's weird just display it
        return {
            status: 'warning',
            status_reason: 'Got an unexpected non-boolean value (`{{raw_value}}`) from the brig federation domain target.',
            fix_hint: '1. Check the brig federation domain target output in the gatherer JSONL\n2. Expected a boolean (`true`/`false`), got a string instead\n3. Verify the gatherer target `brig_federation_domain` is working correctly\n4. Check the brig ConfigMap: `kubectl get configmap brig -o yaml | grep setFederationDomain`',
            recommendation: 'Got an unexpected value from the brig federation domain check.',
            display_value: String(val),
            raw_output: point.raw_output,
            template_data: { raw_value: String(val) },
        }
    }
}

export default BrigFederationDomainChecker
