/**
 * Verifies Backoffice/Stern is not exposed via public ingress.
 *
 * Looks at the security/stern_not_exposed target (boolean or string).
 * Stern is an admin tool that gives unauthenticated read/delete access
 * to the entire user database. It should only be reachable via kubectl
 * port-forward, never public.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class SternNotExposedChecker extends BaseChecker {
    readonly path: string = 'security/stern_not_exposed'
    readonly name: string = 'Backoffice/Stern not exposed via public ingress'
    readonly category: string = 'Security / Hardening'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Ensures the **Backoffice/Stern** admin tool is not reachable via public ingress. Stern provides **unauthenticated** read/delete access to the entire user database and must only be accessed through `kubectl port-forward`.'

    check(data: DataLookup): CheckResult {
        const point = data.get('security/stern_not_exposed')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `security/stern_not_exposed` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can check ingress resources: `kubectl get ingress -n wire`\n2. Ensure the gatherer has permissions to list ingress rules\n3. Review the gatherer logs for errors during the Stern exposure check',
                recommendation: 'Backoffice/Stern not exposed via public ingress data not collected.',
            }
        }

        // Gatherer failed to reach the endpoint — value is null
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Stern exposure check returned null.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value: only treat as healthy if the string matches a known safe pattern.
        // Stern gives unauthenticated read/delete access to the entire user database,
        // so we must not blindly trust arbitrary strings as "not exposed".
        if (typeof val === 'string') {
            if (val.length === 0) {
                return {
                    status: 'gather_failure',
                    status_reason: 'Stern exposure check returned empty result.',
                    raw_output: point.raw_output,
                }
            }

            // Coerce boolean strings before pattern matching — Python serializes booleans
            // as "true"/"false" strings. Apply the same semantics as the boolean branch:
            // true = not exposed (healthy), false = exposed (unhealthy).
            const lower: string = val.toLowerCase().trim()
            if (lower === 'true') {
                return {
                    status: 'healthy',
                    status_reason: 'Stern/Backoffice is not exposed via public ingress.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }
            if (lower === 'false') {
                return {
                    status: 'unhealthy',
                    status_reason: 'Stern/Backoffice is reachable via public ingress.',
                    recommendation: 'Stern is exposed via public ingress. It gives unauthenticated read/delete access to your user database. Use only `kubectl port-forward`.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            const safe_patterns: string[] = [
                'not exposed',
                'no ingress found',
                'no ingress',
                'blocked',
                'not reachable',
                'not found',
            ]
            const is_safe: boolean = safe_patterns.some(pattern => lower.includes(pattern))

            if (is_safe) {
                return {
                    status: 'healthy',
                    status_reason: 'Stern/Backoffice is **not exposed** via public ingress: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            // String does not match any known safe pattern — could indicate exposure
            return {
                status: 'warning',
                status_reason: `Stern exposure check returned an unrecognized result that may indicate exposure: ${val}.`,
                recommendation: 'Verify manually that Stern/Backoffice is not reachable via public ingress. It gives unauthenticated read/delete access to the entire user database.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // true means Stern is not exposed (good)
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Stern/Backoffice is **not exposed** via public ingress.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // false means Stern is exposed (bad)
        return {
            status: 'unhealthy',
            status_reason: 'Stern/Backoffice is **reachable via public ingress** -- this is a critical security issue.',
            fix_hint: '1. Immediately remove the Stern/Backoffice ingress rule:\n   ```\n   kubectl delete ingress stern-ingress -n wire\n   ```\n2. Verify it is no longer reachable from outside: `curl -sI https://stern.<your-domain>/`\n3. Access Stern only through `kubectl port-forward`:\n   ```\n   kubectl port-forward -n wire svc/stern 8080:8080\n   ```\n4. Audit access logs for any unauthorized access while it was exposed',
            recommendation: 'Stern is exposed via public ingress. It gives unauthenticated read/delete access to your user database. Use only `kubectl port-forward`.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default SternNotExposedChecker
