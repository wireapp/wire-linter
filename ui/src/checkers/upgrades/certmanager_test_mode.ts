/**
 * Verifies that cert-manager isn't in test mode.
 *
 * The config/certmanager_test_mode target returns a boolean indicating
 * whether production mode is active. When test mode is on, Let's Encrypt
 * issues staging certificates that browsers won't trust. True means
 * everything is fine (production mode), false means test mode is active.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class CertmanagerTestModeChecker extends BaseChecker {
    readonly path: string = 'upgrades/certmanager_test_mode'
    readonly name: string = 'Cert-manager not in test mode'
    readonly category: string = 'Upgrades / Migrations'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Detects whether **cert-manager** is using Let\'s Encrypt **staging** instead of production. Staging certificates are not trusted by browsers, so clients will see TLS warnings and may be unable to connect.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/certmanager_test_mode')

        // We couldn't gather the target data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `config/certmanager_test_mode` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can access cert-manager resources: `kubectl get clusterissuers`\n2. Check that cert-manager is installed: `kubectl get pods -n cert-manager`\n3. Review the gatherer logs for permission errors',
                recommendation: 'Cert-manager not in test mode data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cert-manager test mode data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Cert-manager test mode target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val = coerce_boolean(point.value)

        // coerce_boolean returns the original value unchanged for types it can't convert
        if (typeof val !== 'boolean') {
            return {
                status: 'gather_failure',
                status_reason: `Cert-manager test mode value could not be interpreted as a boolean (got ${JSON.stringify(point.value)}).`,
                raw_output: point.raw_output,
            }
        }

        // True means we're in production mode (healthy)
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Cert-manager is in **production mode**, using trusted Let\'s Encrypt certificates.',
                display_value: 'production mode',
                raw_output: point.raw_output,
            }
        }

        // False means test mode is on and browsers won't trust the staging certs
        return {
            status: 'unhealthy',
            status_reason: 'Cert-manager is in **test mode**, issuing untrusted Let\'s Encrypt **staging** certificates.',
            fix_hint: '1. Check the current ClusterIssuer configuration:\n   ```\n   kubectl get clusterissuers -o yaml\n   ```\n2. Switch the ACME server URL from staging to production:\n   - **Staging**: `https://acme-staging-v02.api.letsencrypt.org/directory`\n   - **Production**: `https://acme-v02.api.letsencrypt.org/directory`\n3. Update your cert-manager ClusterIssuer:\n   ```\n   kubectl edit clusterissuer letsencrypt-prod\n   ```\n4. Delete existing staging certificates so they get re-issued:\n   ```\n   kubectl delete certificates --all -n wire\n   ```\n5. Verify new certificates are trusted: `curl -vI https://<your-domain>/`',
            recommendation: 'Cert-manager is in test mode. Let\'s Encrypt issues staging certs that browsers won\'t trust.',
            display_value: 'test mode active',
            raw_output: point.raw_output,
        }
    }
}

export default CertmanagerTestModeChecker
