/**
 * Flags containers running as root or in privileged mode.
 *
 * Privileged containers can escape their sandbox. Running as root
 * inside the container increases the blast radius of a compromise.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

interface SecurityIssue {
    service: string
    container: string
    issues: string[]
}

export class SecurityContextChecker extends BaseChecker {
    readonly path: string = 'kubernetes/security_context'
    readonly name: string = 'Container security context'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string =
        'Containers running in **privileged mode** can escape their sandbox. Running as ' +
        '**root** (UID 0) inside the container increases the blast radius if the ' +
        'container is compromised.'

    check(data: DataLookup): CheckResult {
        const issues: SecurityIssue[] = []
        let services_checked: number = 0
        const raw_outputs: string[] = []

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            if (point.raw_output) raw_outputs.push(point.raw_output)

            let details: {
                containers?: {
                    name: string
                    security_context: {
                        privileged?: boolean
                        runAsUser?: number
                        runAsNonRoot?: boolean
                    } | null
                }[]
            }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            for (const container of details.containers ?? []) {
                const ctx = container.security_context
                const container_issues: string[] = []

                if (ctx?.privileged === true) {
                    container_issues.push('privileged mode')
                }

                if (ctx?.runAsUser === 0) {
                    container_issues.push('running as root (UID 0)')
                }

                // No security context at all is not ideal but not critical
                // Only flag explicit dangerous settings

                if (container_issues.length > 0) {
                    issues.push({ service, container: container.name, issues: container_issues })
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
                .map((i: SecurityIssue) => `**${i.service}**/${i.container}: ${i.issues.join(', ')}`)
                .join('\n- ')

            return {
                status: 'warning',
                status_reason: `{{issue_count}} container(s) have security concerns.`,
                fix_hint: 'Set security context in your Helm values:\n```yaml\nsecurityContext:\n  runAsNonRoot: true\n  runAsUser: 1000\n  privileged: false\n  readOnlyRootFilesystem: true\n```',
                recommendation: `Security issues:\n- ${summary}`,
                display_value: `${issues.length} issue(s)`,
                raw_output: raw_outputs.join('\n') || undefined,
                template_data: { issue_count: issues.length },
            }
        }

        return {
            status: 'healthy',
            status_reason: `No privileged or root containers across ${services_checked} service(s).`,
            display_value: `${services_checked} OK`,
            raw_output: raw_outputs.join('\n') || undefined,
            template_data: { issue_count: 0 },
        }
    }
}

export default SecurityContextChecker
