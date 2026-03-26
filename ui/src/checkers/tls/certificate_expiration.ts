/**
 * Checks when the TLS certificate for the main domain expires.
 *
 * We get the days left until expiry from the gatherer. Less than 14 days?
 * That's critical, renew now. Less than 30 days? Warning, plan it soon.
 * Beyond 30 days? You're good.
 *
 * Also handles the case where the gatherer couldn't reach the certificate at all
 * (usually means port 443 is blocked or cert-manager hasn't provisioned yet).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class CertificateExpirationChecker extends BaseChecker {
    readonly path: string = 'tls/certificate_expiration'
    readonly name: string = 'TLS certificate expiration date'
    readonly category: string = 'TLS / Certificates'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Checks how many days remain before the **main domain TLS certificate** expires. Expired certificates cause immediate service outages as all clients refuse to connect.'

    check(data: DataLookup): CheckResult {
        // This check only works when run from outside the network.
        // Check before get() so the sentinel doesn't pollute the accessed points list.
        if (data.is_not_applicable('tls/certificate_expiration')) {
            return {
                status: 'not_applicable',
                status_reason: 'This check requires an external network perspective and was not applicable for this run.',
                recommendation: 'This check requires running the gatherer from an internet-connected machine. Re-run with --source external to verify the TLS certificate from outside.',
            }
        }

        const point = data.get('tls/certificate_expiration')

        // Target was not collected or not applicable for this run
        if (!point) {
            // This check only works when run from outside the network
            if (data.is_not_applicable('tls/certificate_expiration')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'This check requires an **external network perspective** and was not applicable for this run.',
                    recommendation: 'This check requires running the gatherer from an internet-connected machine. Re-run with --source external to verify the TLS certificate from outside.',
                }
            }

            return {
                status: 'gather_failure',
                status_reason: 'TLS certificate expiration data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with network access to the target domain on port **443**.\n2. Re-run the gatherer and check its logs for connection errors:\n   ```\n   python3 src/script/runner.py --target tls/certificate_expiration\n   ```\n3. Ensure `openssl` is installed on the admin host.',
                recommendation: 'TLS certificate expiration date data not collected.',
            }
        }

        // If the gatherer hit an error trying to get the cert, metadata.error will be set
        const collection_error: string | undefined = point.metadata?.error
        if (collection_error) {
            return {
                status: 'gather_failure',
                status_reason: 'TLS certificate could not be checked: **{{collection_error}}**.',
                fix_hint: '1. Test connectivity to the domain from the admin host:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> </dev/null 2>&1\n   ```\n2. If port **443** is unreachable, check firewall rules and load balancer configuration.\n3. If cert-manager is in use, verify the `Certificate` resource status:\n   ```\n   kubectl get certificates -A\n   kubectl describe certificate <name> -n <namespace>\n   ```\n4. If using a self-signed or staging certificate, ensure the gatherer is configured to accept it.',
                recommendation: [
                    `TLS certificate could not be checked: ${collection_error}`,
                    '',
                    'Possible causes:',
                    '  - Port 443 not reachable from the admin host',
                    '  - Certificate not yet installed (cert-manager still provisioning)',
                    '  - Self-signed/staging certificate rejected by openssl',
                    '  - openssl not available on the admin host',
                ].join('\n'),
                display_value: 'check failed',
                // Show the error so the Details button appears
                raw_output: point.raw_output || collection_error,
                template_data: { collection_error },
            }
        }

        // Collection ran but the command failed (and no metadata.error was set)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'TLS certificate expiration data was collected but contained no value.',
                recommendation: 'Certificate expiration target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // We got a number back, that's days left
        if (typeof val === 'number') {
            // Less than 2 weeks? That's bad
            if (val < 14) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Certificate expires in **{{val}}** days, which is below the **14-day** critical threshold.',
                    fix_hint: '1. Renew the TLS certificate **immediately**.\n2. If using cert-manager, check the `Certificate` resource:\n   ```\n   kubectl get certificates -A\n   kubectl describe certificate <name> -n <namespace>\n   ```\n3. If managing certificates manually, request a new certificate and install it.\n4. Verify the renewal with:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> </dev/null 2>&1 | openssl x509 -noout -dates\n   ```',
                    recommendation: `TLS certificate expires in ${val} days. Renew immediately.`,
                    display_value: val,
                    display_unit: 'days',
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // Less than a month? Getting close
            if (val < 30) {
                return {
                    status: 'warning',
                    status_reason: 'Certificate expires in **{{val}}** days, which is below the **30-day** warning threshold.',
                    fix_hint: '1. Plan TLS certificate renewal within the next **{{val}}** days.\n2. If using cert-manager, verify auto-renewal is configured:\n   ```\n   kubectl get certificates -A\n   kubectl describe certificate <name> -n <namespace>\n   ```\n3. If managing certificates manually, initiate the renewal process now.\n4. Check current expiry date:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> </dev/null 2>&1 | openssl x509 -noout -dates\n   ```',
                    recommendation: `TLS certificate expires in ${val} days. Plan renewal soon.`,
                    display_value: val,
                    display_unit: 'days',
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // More than a month? You're fine
            return {
                status: 'healthy',
                status_reason: 'Certificate expires in **{{val}}** days, well above the **30-day** warning threshold.',
                display_value: val,
                display_unit: 'days',
                raw_output: point.raw_output,
                template_data: { val },
            }
        }

        // String value, might have info about the cert
        if (typeof val === 'string') {
            if (val.toLowerCase().includes('expired')) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Certificate status indicates it has expired: "{{val}}".',
                    fix_hint: '1. The TLS certificate has **expired** and must be renewed immediately.\n2. If using cert-manager, check why auto-renewal failed:\n   ```\n   kubectl get certificates -A\n   kubectl describe certificate <name> -n <namespace>\n   kubectl logs -n cert-manager deploy/cert-manager\n   ```\n3. If managing certificates manually, request and install a new certificate.\n4. Verify the new certificate:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> </dev/null 2>&1 | openssl x509 -noout -dates\n   ```',
                    recommendation: 'TLS certificate has expired. Renew immediately.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // String without "expired" in it, treat as good
            return {
                status: 'healthy',
                status_reason: 'Certificate status reported as: "{{val}}".',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { val },
            }
        }

        // If it's literally true, cert is good
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Certificate check returned **true**, indicating a valid certificate.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // False without an error message means something went wrong
        return {
            status: 'unhealthy',
            status_reason: 'Certificate check returned **false**, indicating the certificate is invalid or missing.',
            fix_hint: '1. Verify a valid TLS certificate is installed for the domain:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> </dev/null 2>&1 | openssl x509 -noout -text\n   ```\n2. Ensure the domain resolves correctly: `dig <domain>`\n3. If using cert-manager, check the `Certificate` and `CertificateRequest` resources:\n   ```\n   kubectl get certificates -A\n   kubectl get certificaterequests -A\n   ```\n4. Check cert-manager logs for issuance errors:\n   ```\n   kubectl logs -n cert-manager deploy/cert-manager\n   ```',
            recommendation: 'TLS certificate check failed. Verify that a valid TLS certificate is installed and that the domain resolves correctly.',
            display_value: 'check failed',
            raw_output: point.raw_output,
        }
    }
}

export default CertificateExpirationChecker
