/**
 * Makes sure the TLS certificate chain is complete and valid.
 *
 * The tls/chain_validity target tells us if the server is presenting
 * the full chain (root -> intermediate -> leaf). If it's incomplete,
 * desktop browsers might still work because they cache intermediates,
 * but mobile clients and strict validators will fail.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ChainValidityChecker extends BaseChecker {
    readonly path: string = 'tls/chain_validity'
    readonly name: string = 'TLS certificate chain validity'
    readonly category: string = 'TLS / Certificates'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the server presents a **complete TLS certificate chain** (root, intermediate, leaf). Incomplete chains may work in desktop browsers that cache intermediates but break mobile clients and strict TLS validators.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('tls/chain_validity') ?? data.get_applicable('direct/tls/chain_validity')

        // No data from either the SSH or direct (kubernetes) path
        if (!point) {
            // get_applicable() filters out not_applicable sentinels, so check
            // whether the SSH target was intentionally skipped (e.g. admin host)
            if (data.is_not_applicable('tls/chain_validity')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'This check requires an external network perspective and was not applicable for this run.',
                    recommendation: 'This check requires running the gatherer from an internet-connected machine. Re-run with --source external to verify the TLS certificate chain from outside.',
                }
            }

            return {
                status: 'gather_failure',
                status_reason: 'TLS certificate chain validity data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with network access to the target domain on port **443**.\n2. Re-run the gatherer and check its logs for connection errors:\n   ```\n   python3 src/script/runner.py --target tls/chain_validity\n   ```\n3. Ensure `openssl` is installed on the admin host.',
                recommendation: 'TLS certificate chain validity data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'TLS chain validity data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'TLS chain validity target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // If we got a string, check if it says the chain is broken
        if (typeof val === 'string') {
            const lower: string = val.toLowerCase()

            if (lower.includes('incomplete') || lower.includes('error')) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Certificate chain reported as: "{{val}}".',
                    fix_hint: '1. Inspect the certificate chain served by the domain:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> -showcerts </dev/null 2>&1\n   ```\n2. Verify the chain includes **root**, **intermediate**, and **leaf** certificates in the correct order.\n3. If intermediates are missing, concatenate them into the certificate file:\n   ```\n   cat leaf.crt intermediate.crt > fullchain.crt\n   ```\n4. If using cert-manager, check the `Certificate` resource for chain configuration issues:\n   ```\n   kubectl describe certificate <name> -n <namespace>\n   ```\n5. After fixing, verify the chain with: `openssl verify -CAfile ca-bundle.crt fullchain.crt`',
                    recommendation: 'TLS certificate chain is incomplete or invalid. Missing intermediates work in some browsers but break on mobile or strict clients.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // String with no error keywords, so chain is fine
            return {
                status: 'healthy',
                status_reason: 'Certificate chain validation returned: "{{val}}".',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { val },
            }
        }

        // True means the chain is there and working
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Certificate chain is **complete and valid**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // False or anything falsy means the chain is missing pieces
        return {
            status: 'unhealthy',
            status_reason: 'Certificate chain validation returned **false**, indicating an incomplete or invalid chain.',
            fix_hint: '1. Inspect the certificate chain served by the domain:\n   ```\n   openssl s_client -connect <domain>:443 -servername <domain> -showcerts </dev/null 2>&1\n   ```\n2. Verify the chain includes **root**, **intermediate**, and **leaf** certificates.\n3. If intermediates are missing, concatenate them into the certificate file:\n   ```\n   cat leaf.crt intermediate.crt > fullchain.crt\n   ```\n4. If using cert-manager, check the `Certificate` resource:\n   ```\n   kubectl describe certificate <name> -n <namespace>\n   ```\n5. After fixing, verify: `openssl verify -CAfile ca-bundle.crt fullchain.crt`',
            recommendation: 'TLS certificate chain is incomplete or invalid. Missing intermediates work in some browsers but break on mobile or strict clients.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default ChainValidityChecker
