/**
 * Verifies internal /i/ endpoints are blocked from external access.
 *
 * Looks at the security/internal_endpoints_blocked target (boolean or string).
 * The endpoints /i/users, /i/oauth/clients, and /i/legalhold must not be
 * reachable from outside since they bypass authentication.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class InternalEndpointsChecker extends BaseChecker {
    readonly path: string = 'security/internal_endpoints'
    readonly data_path: string = 'security/internal_endpoints_blocked'
    readonly name: string = 'Internal /i/ endpoints not reachable from outside'
    readonly category: string = 'Security / Hardening'
    readonly interest = 'Setup' as const

    readonly explanation: string = 'Confirms that internal /i/ endpoints (/i/users, /i/oauth/clients, /i/legalhold) are blocked from external access. These endpoints bypass authentication entirely and would allow unauthorized user data access if exposed.'

    check(data: DataLookup): CheckResult {
        // Try the SSH variant first; fall back to the direct-HTTP variant
        // which works in only_through_kubernetes mode
        const point = data.get_applicable('security/internal_endpoints_blocked')
            ?? data.get_applicable('direct/security/internal_endpoints_blocked')

        // Neither variant collected usable data
        if (!point) {
            // If the SSH variant exists but is not_applicable, report that
            if (data.is_not_applicable('security/internal_endpoints_blocked')
                || data.is_not_applicable('direct/security/internal_endpoints_blocked')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'Gatherer ran from inside the network and cannot simulate an external attacker.',
                    recommendation: 'Run the gatherer from outside the network to check if internal endpoints are blocked. Use --source external to verify this.',
                }
            }

            return {
                status: 'gather_failure',
                status_reason: 'Target data for `security/internal_endpoints_blocked` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has **external network access** to test endpoint reachability\n2. Check that `curl` is available on the gatherer host\n3. Review the gatherer logs for connection errors or DNS resolution failures',
                recommendation: 'Internal /i/ endpoints not reachable from outside data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // Build a recommendation that references the actual deployment domain
        // so the operator knows exactly which URLs are exposed
        const domain: string = data.config?.cluster.domain ?? ''
        const endpoints: string = domain
            ? `https://nginz-https.${domain}/i/users, https://nginz-https.${domain}/i/oauth/clients, https://nginz-https.${domain}/i/legalhold`
            : '/i/users, /i/oauth/clients, /i/legalhold'
        const fail_recommendation: string = `Internal /i/ endpoints are reachable from outside. Block ${endpoints} immediately - they bypass authentication and should never be externally accessible.`

        // String value requires content inspection — a non-empty string might
        // describe endpoints being accessible rather than blocked
        if (typeof val === 'string') {
            if (val.length > 0) {
                // Patterns that indicate endpoints are exposed, not blocked.
                // The Python gatherer produces strings like "SECURITY: Internal
                // endpoints accessible: /i/users (HTTP 200)" when endpoints are
                // reachable via success HTTP codes (1xx/2xx/3xx).
                const lower: string = val.toLowerCase()
                const exposure_indicators: string[] = [
                    'accessible',
                    'reachable',
                    'not blocked',
                    'exposed',
                    'http 1',    // 1xx responses
                    'http 2',    // 2xx responses
                    'http 3',    // 3xx responses
                    '200 ok',
                    'returned 200',
                ]
                const is_exposed: boolean = exposure_indicators.some(
                    (indicator: string) => lower.includes(indicator)
                )

                if (is_exposed) {
                    return {
                        status: 'unhealthy',
                        status_reason: `Internal /i/ endpoints appear reachable from outside: ${val}`,
                        recommendation: fail_recommendation,
                        display_value: val,
                        raw_output: point.raw_output,
                    }
                }

                return {
                    status: 'healthy',
                    status_reason: 'Internal `/i/` endpoints are **blocked** from external access: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'Internal `/i/` endpoints ({{endpoints}}) are **reachable from outside** the cluster.',
                fix_hint: '1. Add ingress rules to block all `/i/` paths from external access:\n   ```yaml\n   # In your nginz ingress configuration:\n   nginx.ingress.kubernetes.io/server-snippet: |\n     location ~* ^/i/ {\n       return 403;\n     }\n   ```\n2. Verify the endpoints are blocked from outside:\n   ```\n   curl -sI https://nginz-https.{{domain}}/i/users\n   ```\n   Expected: connection refused or 403\n3. These endpoints bypass authentication -- treat this as a **critical security issue**',
                recommendation: fail_recommendation,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { endpoints, domain },
            }
        }

        // true means endpoints are blocked (safe)
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All internal `/i/` endpoints are **blocked** from external access.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // false means endpoints are exposed (dangerous)
        return {
            status: 'unhealthy',
            status_reason: 'Internal `/i/` endpoints ({{endpoints}}) are **reachable from outside** the cluster.',
            fix_hint: '1. Add ingress rules to block all `/i/` paths from external access:\n   ```yaml\n   # In your nginz ingress configuration:\n   nginx.ingress.kubernetes.io/server-snippet: |\n     location ~* ^/i/ {\n       return 403;\n     }\n   ```\n2. Verify the endpoints are blocked from outside:\n   ```\n   curl -sI https://nginz-https.{{domain}}/i/users\n   ```\n   Expected: connection refused or 403\n3. These endpoints bypass authentication -- treat this as a **critical security issue**',
            recommendation: fail_recommendation,
            display_value: val,
            raw_output: point.raw_output,
            template_data: { endpoints, domain },
        }
    }
}

export default InternalEndpointsChecker
