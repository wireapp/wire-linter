/**
 * Verifies all required Kubernetes secrets are present and non-empty.
 *
 * Looks at the secrets/required_present target (boolean or string).
 * This includes zAuth keys (brig+nginz), TURN secret, SMTP password,
 * RabbitMQ credentials, PG password, MinIO keys, and the TLS wildcard
 * cert+key. Without them, services crash on startup.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class RequiredPresentChecker extends BaseChecker {
    readonly path: string = 'secrets/required_present'
    readonly name: string = 'All required K8s Secrets present and non-empty'
    readonly category: string = 'Secrets / Credentials'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that all required **Kubernetes secrets** (`zAuth` keys, `TURN` secret, SMTP password, RabbitMQ credentials, TLS certs) exist and are non-empty. Missing secrets cause services to **crash on startup**.'

    check(data: DataLookup): CheckResult {
        const point = data.get('secrets/required_present')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `secrets/required_present` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has **kubectl access** to the cluster\n2. Check that the gatherer can run `kubectl get secrets -n wire`\n3. Review the gatherer logs for permission errors or timeouts',
                recommendation: 'All required K8s Secrets present and non-empty data not collected.',
            }
        }

        // Data point exists but value is null — gatherer could not reach the cluster
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Secrets presence data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Required secrets target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean

        // Extract specific missing secrets from health_info for status_reason
        const missing_issues: string = this._extract_issues(point)

        // String value non-empty means all secrets are present
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'All required K8s secrets are **present** and non-empty.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: missing_issues
                    ? 'Required K8s secrets are **missing**: {{missing_issues}}.'
                    : 'One or more required K8s secrets are **missing or empty**.',
                fix_hint: missing_issues
                    ? '1. List the current secrets in the Wire namespace:\n   ```\n   kubectl get secrets -n wire\n   ```\n2. Create the missing secrets ({{missing_issues}}) using the Wire installation guide\n3. For TLS secrets, verify the certificate and key files are valid before creating the secret:\n   ```\n   openssl x509 -in tls.crt -noout -text\n   ```\n4. Restart affected pods after creating the secrets: `kubectl rollout restart deployment -n wire`'
                    : '1. List the current secrets in the Wire namespace:\n   ```\n   kubectl get secrets -n wire\n   ```\n2. Compare against the required secrets list: `zAuth` keys, `TURN` secret, SMTP password, RabbitMQ credentials, TLS certs\n3. Create any missing secrets following the Wire installation guide\n4. Restart affected pods after creating the secrets: `kubectl rollout restart deployment -n wire`',
                recommendation: this._build_missing_recommendation(point),
                display_value: val,
                raw_output: point.raw_output,
                template_data: { missing_issues },
            }
        }

        // Boolean true means all secrets are present
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All required K8s secrets are **present** and non-empty.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false some secrets are missing
        return {
            status: 'unhealthy',
            status_reason: missing_issues
                ? 'Required K8s secrets are **missing**: {{missing_issues}}.'
                : 'One or more required K8s secrets are **missing or empty**.',
            fix_hint: missing_issues
                ? '1. List the current secrets in the Wire namespace:\n   ```\n   kubectl get secrets -n wire\n   ```\n2. Create the missing secrets ({{missing_issues}}) using the Wire installation guide\n3. For TLS secrets, verify the certificate and key files are valid before creating the secret:\n   ```\n   openssl x509 -in tls.crt -noout -text\n   ```\n4. Restart affected pods after creating the secrets: `kubectl rollout restart deployment -n wire`'
                : '1. List the current secrets in the Wire namespace:\n   ```\n   kubectl get secrets -n wire\n   ```\n2. Compare against the required secrets list: `zAuth` keys, `TURN` secret, SMTP password, RabbitMQ credentials, TLS certs\n3. Create any missing secrets following the Wire installation guide\n4. Restart affected pods after creating the secrets: `kubectl rollout restart deployment -n wire`',
            recommendation: this._build_missing_recommendation(point),
            display_value: val,
            raw_output: point.raw_output,
            template_data: { missing_issues },
        }
    }

    /** Extract the comma-separated issues list from health_info, or empty string if not available. */
    private _extract_issues(point: { metadata?: { health_info?: string } }): string {
        const health_info: string = point.metadata?.health_info ?? ''
        const issues_match: RegExpMatchArray | null = health_info.match(/Issues:\s*(.+)/)
        return issues_match?.[1] ?? ''
    }

    /** Extract specific missing secrets from the collector's health_info and build a targeted recommendation. */
    private _build_missing_recommendation(point: { metadata?: { health_info?: string } }): string {
        const health_info: string = point.metadata?.health_info ?? ''

        // format: «Issues: brig-secrets, nginz-secrets, brig-turn, wire-server-tls»
        const issues_match: RegExpMatchArray | null = health_info.match(/Issues:\s*(.+)/)
        const specific_issues: string = issues_match?.[1] ?? ''

        if (specific_issues) {
            return `Missing or incomplete K8s secrets: ${specific_issues}. Services will crash on startup without these.`
        }

        return 'Required K8s secrets are missing. Services crash on startup without them.'
    }
}

export default RequiredPresentChecker
