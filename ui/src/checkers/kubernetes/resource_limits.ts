/**
 * Flags Wire services missing CPU/memory resource limits or requests.
 *
 * Without limits, a single pod can OOM-kill the node. Without requests,
 * the scheduler can't make good placement decisions.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

interface ContainerIssue {
    service: string
    container: string
    missing: string[]
}

export class ResourceLimitsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/resource_limits'
    readonly name: string = 'Resource limits & requests'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string =
        'Containers without **memory/CPU limits** can consume unbounded resources, ' +
        'potentially OOM-killing the entire node. Without **requests**, the Kubernetes ' +
        'scheduler cannot make informed placement decisions.'

    check(data: DataLookup): CheckResult {
        const issues: ContainerIssue[] = []
        let services_checked: number = 0
        const raw_outputs: string[] = []

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            if (point.raw_output) raw_outputs.push(point.raw_output)

            let details: { containers?: { name: string; resources: { requests: Record<string, string>; limits: Record<string, string> } }[] }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            for (const container of details.containers ?? []) {
                const missing: string[] = []
                const requests = container.resources?.requests ?? {}
                const limits = container.resources?.limits ?? {}

                if (!limits.memory) missing.push('memory limit')
                if (!limits.cpu) missing.push('cpu limit')
                if (!requests.memory) missing.push('memory request')
                if (!requests.cpu) missing.push('cpu request')

                if (missing.length > 0) {
                    issues.push({ service, container: container.name, missing })
                }
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment details data collected.',
                fix_hint: 'Ensure the gatherer has kubectl access and re-run with Kubernetes targets enabled.',
            }
        }

        if (issues.length > 0) {
            // Separate missing limits (dangerous) from missing requests (bad practice)
            const missing_limits: ContainerIssue[] = issues.filter(
                (i: ContainerIssue) => i.missing.some((m: string) => m.includes('limit'))
            )
            const summary: string = issues
                .map((i: ContainerIssue) => `**${i.service}**/${i.container}: ${i.missing.join(', ')}`)
                .join('\n- ')

            return {
                status: missing_limits.length > 0 ? 'unhealthy' : 'warning',
                status_reason: `{{issue_count}} container(s) missing resource configuration.`,
                fix_hint: 'Set resource limits and requests in your Helm values:\n```yaml\nresources:\n  limits:\n    memory: "512Mi"\n    cpu: "500m"\n  requests:\n    memory: "256Mi"\n    cpu: "100m"\n```\nThen run `helm upgrade` to apply.',
                recommendation: `Missing resources:\n- ${summary}`,
                display_value: `${issues.length} issue(s)`,
                raw_output: raw_outputs.join('\n') || undefined,
                template_data: { issue_count: issues.length },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All containers across ${services_checked} service(s) have resource limits and requests configured.`,
            display_value: `${services_checked} OK`,
            raw_output: raw_outputs.join('\n') || undefined,
            template_data: { issue_count: 0 },
        }
    }
}

export default ResourceLimitsChecker
