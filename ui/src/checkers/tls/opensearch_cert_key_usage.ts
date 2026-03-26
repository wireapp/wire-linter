/**
 * Makes sure OpenSearch's TLS certificate has the right key usage extensions.
 *
 * If the certificate is missing digitalSignature and keyEncipherment in keyUsage,
 * or serverAuth in extendedKeyUsage, Java's TLS stack in OpenSearch plugins will
 * reject it and close the connection. We check the tls/opensearch_cert_key_usage target
 * to see if the certificate is set up correctly. See WPB-18068.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class OpensearchCertKeyUsageChecker extends BaseChecker {
    readonly path: string = 'tls/opensearch_cert_key_usage'
    readonly name: string = 'OpenSearch TLS certificate key usage (see: WPB-18068)'
    readonly category: string = 'TLS / Certificates'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Validates that the OpenSearch TLS certificate includes the required **key usage extensions** (`digitalSignature`, `keyEncipherment`, `serverAuth`). Missing extensions cause Java TLS clients to reject connections with cryptic errors.'

    check(data: DataLookup): CheckResult {
        const point = data.get('tls/opensearch_cert_key_usage')

        // We didn't manage to collect this data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'OpenSearch TLS certificate key usage data was not collected.',
                fix_hint: '1. Ensure the gatherer has **SSH access** to a node running OpenSearch.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target tls/opensearch_cert_key_usage\n   ```\n3. Manually inspect the certificate on the OpenSearch node:\n   ```\n   openssl x509 -in /path/to/opensearch-cert.pem -noout -text | grep -A2 "Key Usage"\n   ```',
                recommendation: 'OpenSearch TLS certificate key usage data not collected.',
            }
        }

        const val = point.value as boolean | string

        // True means the certificate has the right key usage
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'OpenSearch certificate has the required `keyUsage` and `extendedKeyUsage` extensions.',
                display_value: 'keyUsage + extKeyUsage OK',
                raw_output: point.raw_output,
            }
        }

        // False means the certificate is missing the extensions it needs
        if (val === false) {
            return {
                status: 'unhealthy',
                status_reason: 'OpenSearch certificate is missing required `keyUsage` or `extendedKeyUsage` extensions.',
                fix_hint: '1. Inspect the current certificate key usage:\n   ```\n   openssl x509 -in /path/to/opensearch-cert.pem -noout -text | grep -A4 "Key Usage"\n   ```\n2. The certificate **must** include:\n   - `keyUsage`: `digitalSignature`, `keyEncipherment`\n   - `extendedKeyUsage`: `serverAuth`\n3. Regenerate the certificate with the correct extensions. Example OpenSSL config snippet:\n   ```\n   [v3_req]\n   keyUsage = digitalSignature, keyEncipherment\n   extendedKeyUsage = serverAuth\n   ```\n4. Replace the certificate on all OpenSearch nodes and restart OpenSearch.\n5. See **WPB-18068** for details on this issue.',
                recommendation: 'OpenSearch TLS certificate is missing required key usage extensions (digitalSignature, keyEncipherment in keyUsage; serverAuth in extendedKeyUsage). Java TLS clients reject this certificate, causing "Remote end closed connection" errors. Regenerate the certificate with the correct extensions.',
                display_value: 'keyUsage mismatch',
                raw_output: point.raw_output,
            }
        }

        // If we got a string back, something's off but show it anyway
        return {
            status: 'warning',
            status_reason: 'Unexpected non-boolean value returned from key usage check: "{{val}}".',
            fix_hint: '1. The key usage check returned an unexpected value instead of a boolean.\n2. Manually verify the certificate key usage:\n   ```\n   openssl x509 -in /path/to/opensearch-cert.pem -noout -text | grep -A4 "Key Usage"\n   ```\n3. Ensure the certificate includes `digitalSignature`, `keyEncipherment`, and `serverAuth`.',
            recommendation: 'Unexpected value from OpenSearch certificate key usage check.',
            display_value: String(val),
            raw_output: point.raw_output,
            template_data: { val },
        }
    }
}

export default OpensearchCertKeyUsageChecker
