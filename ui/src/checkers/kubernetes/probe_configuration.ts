/**
 * Flags containers missing liveness or readiness probes.
 *
 * Without probes, Kubernetes can't detect when a container is dead
 * (liveness) or not ready to serve traffic (readiness). The pod
 * stays "Running" while actually broken.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

interface ProbeIssue {
    service: string
    container: string
    missing: string[]
}

export class ProbeConfigurationChecker extends BaseChecker {
    readonly path: string = 'kubernetes/probe_configuration'
    readonly name: string = 'Liveness & readiness probes'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string =
        'Containers without **liveness probes** can be "Running" but actually dead — ' +
        'Kubernetes won\'t restart them. Without **readiness probes**, traffic gets sent ' +
        'to containers that aren\'t ready to handle it.'

    check(data: DataLookup): CheckResult {
        const issues: ProbeIssue[] = []
        let services_checked: number = 0

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            let details: { containers?: { name: string; liveness_probe: unknown; readiness_probe: unknown }[] }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            for (const container of details.containers ?? []) {
                const missing: string[] = []
                if (!container.liveness_probe) missing.push('liveness probe')
                if (!container.readiness_probe) missing.push('readiness probe')

                if (missing.length > 0) {
                    issues.push({ service, container: container.name, missing })
                }
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment details data collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        if (issues.length > 0) {
            const summary: string = issues
                .map((i: ProbeIssue) => `**${i.service}**/${i.container}: missing ${i.missing.join(', ')}`)
                .join('\n- ')

            return {
                status: 'warning',
                status_reason: `{{issue_count}} container(s) missing health probes.`,
                fix_hint: 'Add probes to your Helm values. Example:\n```yaml\nlivenessProbe:\n  httpGet:\n    path: /i/status\n    port: 8080\n  initialDelaySeconds: 30\nreadinessProbe:\n  httpGet:\n    path: /i/status\n    port: 8080\n```',
                recommendation: `Missing probes:\n- ${summary}`,
                display_value: `${issues.length} missing`,
                template_data: { issue_count: issues.length },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All containers across ${services_checked} service(s) have liveness and readiness probes.`,
            display_value: `${services_checked} OK`,
            template_data: { issue_count: 0 },
        }
    }
}

export default ProbeConfigurationChecker
