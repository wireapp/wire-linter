/**
 * Checks ingress controller response.
 *
 * The ingress controller routes all external traffic. If it's broken, nothing
 * reaches your backend even if the pods are fine.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { is_http_success_keyword, is_http_error_keyword } from '../checker_helpers'

export class IngressResponseChecker extends BaseChecker {
    readonly path: string = 'wire_services/ingress_response'
    readonly name: string = 'Ingress controller response test'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Tests that the **ingress controller** is responding to external HTTP requests. If the ingress is broken, no client traffic reaches the backend even when all pods are running fine.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('wire_services/ingress_response') ?? data.get('direct/wire_services/ingress_response')

        // Didn't get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Ingress controller response data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `ingress_response` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the ingress response check',
                recommendation: 'Ingress controller response test data not collected.',
            }
        }

        // Collection ran but failed (Python collector sets value=null on error)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Ingress response data was collected but contained no value.',
                recommendation: point.metadata?.error
                    ?? 'Ingress response target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        // Value can be boolean, string (HTTP status), or number (HTTP status code)
        const value: boolean | string | number = point.value
        // Build a recommendation that includes the health assessment from the collector
        const health_detail: string = point.metadata?.health_info ?? ''
        const base_recommendation: string = 'Ingress controller not responding. If ingress is broken, all API traffic fails even if backend pods are healthy.'
        const recommendation: string = health_detail
            ? `${base_recommendation} ${health_detail}.`
            : base_recommendation

        // Got a boolean back
        if (typeof value === 'boolean') {
            if (!value) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Ingress controller is **not responding** to HTTP requests.',
                    fix_hint: '1. Check ingress controller pods: `kubectl get pods -n ingress-nginx`\n2. View ingress controller logs: `kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx --tail=100`\n3. Verify ingress resources: `kubectl get ingress -n wire`\n4. Test from within the cluster: `kubectl exec -n wire <any-pod> -- curl -sI http://nginz-https.wire.svc.cluster.local`\n5. Check external DNS resolution and load balancer status',
                    recommendation,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'Ingress controller is responding to HTTP requests.',
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // Got a number probably an HTTP status code
        if (typeof value === 'number') {
            // 2xx responses are fully healthy
            if (value >= 200 && value < 300) {
                return {
                    status: 'healthy',
                    status_reason: 'Ingress controller returned HTTP **{{http_status}}**.',
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { http_status: status_code },
                }
            }

            // 3xx redirects are expected (e.g. HTTP→HTTPS), but worth noting
            if (value >= 300 && value < 400) {
                return {
                    status: 'warning',
                    status_reason: `Ingress controller returned HTTP ${value} redirect.`,
                    recommendation: `Ingress returned a ${value} redirect. This is normal for HTTP→HTTPS redirection but may indicate misconfiguration if the target was already HTTPS.`,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: `Ingress controller returned HTTP ${value}.`,
                recommendation,
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // Got a string — could be an HTTP status code or a descriptive keyword
        if (typeof value === 'string') {
            // Known success keywords from collectors that return text instead of status codes
            if (is_http_success_keyword(value)) {
                return {
                    status: 'healthy',
                    status_reason: `Ingress controller responded with "${value}".`,
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { http_status: status_code },
                }
            }

            // Known error keywords — unhealthy with an accurate status_reason
            if (is_http_error_keyword(value)) {
                return {
                    status: 'unhealthy',
                    status_reason: `Ingress controller could not be reached: ${value}.`,
                    recommendation,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            // Try parsing as a numeric HTTP status code (e.g. "200", "301", "503")
            const numeric_status: number = parseInt(value, 10)

            if (!isNaN(numeric_status)) {
                // 2xx responses are fully healthy
                if (numeric_status >= 200 && numeric_status < 300) {
                    return {
                        status: 'healthy',
                        status_reason: `Ingress controller returned HTTP ${value}.`,
                        display_value: value,
                        raw_output: point.raw_output,
                    }
                }

                // 3xx redirects are expected (e.g. HTTP→HTTPS), but worth noting
                if (numeric_status >= 300 && numeric_status < 400) {
                    return {
                        status: 'warning',
                        status_reason: `Ingress controller returned HTTP ${value} redirect.`,
                        recommendation: `Ingress returned a ${value} redirect. This is normal for HTTP→HTTPS redirection but may indicate misconfiguration if the target was already HTTPS.`,
                        display_value: value,
                        raw_output: point.raw_output,
                    }
                }

                // 4xx/5xx are unhealthy
                return {
                    status: 'unhealthy',
                    status_reason: `Ingress controller returned HTTP ${value}.`,
                    recommendation,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            // Non-numeric, unrecognized string — treat as an error response
            return {
                status: 'unhealthy',
                status_reason: `Ingress controller returned unexpected response: ${value}.`,
                recommendation,
                display_value: value,
                raw_output: point.raw_output,
                template_data: { http_status: status_code },
            }
        }

        // Exhaustive check — all value types are handled above. If DataPoint's
        // value type ever gains a new variant, TypeScript will error here.
        const _exhaustive: never = value
        return _exhaustive
    }
}

export default IngressResponseChecker
