/**
 * Checks Webapp HTTP accessibility.
 *
 * Tests that the webapp is actually reachable via HTTP,
 * the way users load it in their browser.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { is_http_success_keyword, is_http_error_keyword } from '../checker_helpers'

export class WebappHttpChecker extends BaseChecker {
    readonly path: string = 'wire_services/webapp_http'
    readonly name: string = 'Webapp HTTP accessibility'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Webapp** is actually reachable via HTTP, the way end users load it in their browser. A healthy pod does not help if the HTTP endpoint is unreachable due to networking or ingress issues.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('wire_services/webapp_http') ?? data.get('direct/wire_services/webapp_http')

        // Didn't collect data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Webapp HTTP accessibility data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `webapp_http` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Webapp HTTP accessibility check',
                recommendation: 'Webapp HTTP accessibility data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Webapp HTTP accessibility data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Webapp HTTP accessibility target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const value: boolean | string | number = point.value
        // Build a recommendation that includes the health assessment from the collector
        const health_detail: string = point.metadata?.health_info ?? ''
        const base_recommendation: string = 'Webapp is not accessible via HTTP. This is what end users actually load in their browser.'
        const recommendation: string = health_detail
            ? `${base_recommendation} ${health_detail}.`
            : base_recommendation

        // Got a boolean back
        if (typeof value === 'boolean') {
            if (!value) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Webapp is **not reachable** via HTTP.',
                    fix_hint: '1. Check webapp pod status: `kubectl get pods -n wire -l app=webapp`\n2. Verify the webapp service: `kubectl get svc -n wire | grep webapp`\n3. Check ingress configuration: `kubectl describe ingress -n wire | grep webapp`\n4. Test from within the cluster: `kubectl exec -n wire <any-pod> -- curl -sI http://webapp`\n5. Test from outside: `curl -vk https://<webapp-domain>/`\n6. Check DNS resolution: `dig <webapp-domain>`',
                    recommendation,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'Webapp is reachable via HTTP.',
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // Got an HTTP status code
        if (typeof value === 'number') {
            // 2xx responses are fully healthy
            if (value >= 200 && value < 300) {
                return {
                    status: 'healthy',
                    status_reason: 'Webapp returned HTTP **{{http_status}}**.',
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { http_status: value },
                }
            }

            // 3xx redirects are expected (e.g. HTTP→HTTPS), but worth noting
            if (value >= 300 && value < 400) {
                return {
                    status: 'warning',
                    status_reason: `Webapp returned HTTP ${value} redirect.`,
                    recommendation: `Webapp returned a ${value} redirect. This is normal for HTTP→HTTPS redirection but may indicate misconfiguration if the target was already HTTPS.`,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: `Webapp returned HTTP ${value}.`,
                recommendation,
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // Got a string — could be a status code, a success keyword, or a network error
        if (typeof value === 'string') {
            // Known success keywords from collectors that return text instead of status codes
            if (is_http_success_keyword(value)) {
                return {
                    status: 'healthy',
                    status_reason: `Webapp responded with "${value}".`,
                    display_value: value,
                    raw_output: point.raw_output,
                    template_data: { http_status: value },
                }
            }

            // Known error keywords — produce a specific diagnostic rather than "unexpected response"
            if (is_http_error_keyword(value)) {
                return {
                    status: 'unhealthy',
                    status_reason: `Webapp could not be reached: ${value}.`,
                    recommendation,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            const numeric_status: number = parseInt(value, 10)

            if (!isNaN(numeric_status)) {
                // 2xx responses are fully healthy
                if (numeric_status >= 200 && numeric_status < 300) {
                    return {
                        status: 'healthy',
                        status_reason: `Webapp returned HTTP ${value}.`,
                        display_value: value,
                        raw_output: point.raw_output,
                    }
                }

                // 3xx redirects are expected (e.g. HTTP→HTTPS), but worth noting
                if (numeric_status >= 300 && numeric_status < 400) {
                    return {
                        status: 'warning',
                        status_reason: `Webapp returned HTTP ${value} redirect.`,
                        recommendation: `Webapp returned a ${value} redirect. This is normal for HTTP→HTTPS redirection but may indicate misconfiguration if the target was already HTTPS.`,
                        display_value: value,
                        raw_output: point.raw_output,
                    }
                }

                // 4xx/5xx are unhealthy
                return {
                    status: 'unhealthy',
                    status_reason: `Webapp returned HTTP ${value}.`,
                    recommendation,
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            // Non-numeric, unrecognized string — treat as an error response
            return {
                status: 'unhealthy',
                status_reason: `Webapp returned unexpected response: ${value}.`,
                recommendation,
                display_value: value,
                raw_output: point.raw_output,
                template_data: { http_status: value },
            }
        }

        // Exhaustive check — TypeScript will error here if a new variant is added without handling it
        const _exhaustive: never = value
        return _exhaustive
    }
}

export default WebappHttpChecker
