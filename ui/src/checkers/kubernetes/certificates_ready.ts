/**
 * Checks if your TLS certificates are all ready.
 * If any aren't, things like TLS termination and service-to-service
 * encryption will break, which is why we flag it as unhealthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class CertificatesReadyChecker extends BaseChecker {
    readonly path: string = 'kubernetes/certificates_ready'
    readonly name: string = 'TLS certificates ready'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Ensures all **cert-manager Certificate resources** have reached **Ready** status. Certificates stuck in a non-ready state will break TLS termination and service-to-service encryption.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/certificates/all_ready')

        // Didn't manage to get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'TLS certificates readiness data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/certificates/all_ready\n   ```\n3. Manually check: `kubectl get certificates -A`',
                recommendation: 'Couldn\'t collect TLS certificates ready data.',
            }
        }

        // Null means the target ran but produced no usable result
        if (point.value === null || point.value === undefined) {
            return {
                status: 'gather_failure',
                status_reason: 'TLS certificates readiness check returned no result.',
                recommendation: 'The target ran but produced no data. Check whether cert-manager is installed.',
                raw_output: point.raw_output,
            }
        }

        const coerced = coerce_boolean(point.value)

        // coerce_boolean returns the original value if it can't convert to boolean
        if (typeof coerced !== 'boolean') {
            return {
                status: 'gather_failure',
                status_reason: 'TLS certificates readiness returned an unexpected value.',
                recommendation: `Expected a boolean but got: ${JSON.stringify(point.value)}`,
                raw_output: point.raw_output,
            }
        }

        // Some certificates aren't ready TLS could be broken
        if (!coerced) {
            return {
                status: 'unhealthy',
                status_reason: 'One or more cert-manager Certificate resources are **not in Ready state**.',
                fix_hint: '1. List all certificates and their statuses:\n   ```\n   kubectl get certificates -A\n   ```\n2. Describe the non-ready certificate(s):\n   ```\n   kubectl describe certificate <name> -n <namespace>\n   ```\n3. Check cert-manager logs for issuance errors:\n   ```\n   kubectl logs -n cert-manager deploy/cert-manager\n   ```\n4. Common causes:\n   - **Issuer/ClusterIssuer** misconfigured or missing\n   - DNS challenge failing (check DNS provider credentials)\n   - Rate limits on the ACME provider (e.g., Let\'s Encrypt)\n5. Check `CertificateRequest` and `Order` resources for detailed status:\n   ```\n   kubectl get certificaterequests -A\n   kubectl get orders -A\n   ```',
                recommendation: 'Some TLS certificates aren\'t ready. Check the cert-manager logs and your certificate resources.',
                display_value: coerced,
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All cert-manager Certificate resources are in Ready state.',
            display_value: coerced,
            raw_output: point.raw_output,
        }
    }
}

export default CertificatesReadyChecker
