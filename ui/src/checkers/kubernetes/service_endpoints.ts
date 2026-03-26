/**
 * Flags Wire services with zero endpoints (traffic goes nowhere).
 *
 * A Service with 0 endpoints means label selectors don't match any
 * pods, or all pods are unhealthy and failing readiness probes.
 *
 * Consumes: kubernetes/endpoints/service_endpoints/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import { parse_number, type DataLookup } from '../data_lookup'

export class ServiceEndpointsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/service_endpoints'
    readonly name: string = 'Service endpoints'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string =
        'A Kubernetes Service with **zero endpoints** means traffic goes to a black hole. ' +
        'This happens when label selectors don\'t match any pods, all pods are unhealthy ' +
        '(failing readiness probes), or the service is misconfigured.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const empty_services: string[] = []
        const healthy_services: { service: string; endpoints: number }[] = []
        let services_checked: number = 0
        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/endpoints/service_endpoints/${service}`)
            if (!point) continue

            // Null/unparseable value means collection failed — skip rather than treating as zero
            const endpoint_count: number | null = parse_number(point)
            if (endpoint_count === null) continue

            services_checked++

            if (endpoint_count === 0) {
                empty_services.push(service)
            } else {
                healthy_services.push({ service, endpoints: endpoint_count })
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No endpoint data collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        if (empty_services.length > 0) {
            const names: string = empty_services.map((s: string) => `**${s}**`).join(', ')

            // Build kubectl commands directly to avoid Handlebars {{#each}} double-newline issues
            const kubectl_commands: string = empty_services
                .map((s: string) => `kubectl get pods -l app=${s} -n ${ns}\nkubectl describe endpoints/${s} -n ${ns}`)
                .join('\n')

            return {
                status: 'unhealthy',
                // Build status_reason directly — names contains Markdown bold markers
                // that Handlebars would HTML-escape
                status_reason: `${empty_services.length} service(s) have zero endpoints: ${names}.`,
                fix_hint: `Check if pods exist and are passing readiness probes:\n\`\`\`\n${kubectl_commands}\n\`\`\``,
                display_value: `${empty_services.length} empty`,
                template_data: {
                    empty_count: empty_services.length,
                    names,
                    empty_services,
                },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All ${services_checked} service(s) have active endpoints.`,
            display_value: `${services_checked} OK`,
            template_data: { empty_count: 0, names: '', empty_services: [] },
        }
    }
}

export default ServiceEndpointsChecker
