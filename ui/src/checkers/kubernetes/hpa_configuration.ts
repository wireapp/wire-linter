/**
 * Reports HPA configuration and flags potential issues.
 *
 * HPAs that are pegged at max replicas may indicate the service can't
 * keep up with load. HPAs with minReplicas=1 defeat high availability.
 *
 * Consumes: kubernetes/hpa/configuration
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class HpaConfigurationChecker extends BaseChecker {
    readonly path: string = 'kubernetes/hpa_configuration'
    readonly name: string = 'HPA configuration'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/hpa/configuration'
    readonly explanation: string =
        '**Horizontal Pod Autoscalers** auto-scale services based on CPU/memory metrics. ' +
        'Misconfigured HPAs can leave services under-provisioned (maxReplicas too low) ' +
        'or without HA (minReplicas=1). Services pegged at maxReplicas may be struggling.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const point = data.get('kubernetes/hpa/configuration')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'HPA data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            hpa_count?: number
            hpas?: {
                name: string
                target_name: string
                min_replicas: number
                max_replicas: number
                current_replicas: number
                desired_replicas: number
            }[]
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse HPA data.', raw_output: point.raw_output }
        }

        const hpa_count: number = parsed.hpa_count ?? 0

        // No HPAs is not necessarily a problem — many deployments use fixed replicas
        if (hpa_count === 0) {
            return {
                status: 'healthy',
                status_reason: 'No HPAs configured. Services use fixed replica counts.',
                display_value: 'none',
                raw_output: point.raw_output,
            }
        }

        const issues: string[] = []
        const hpas = parsed.hpas ?? []

        // Check for HPAs pegged at max
        const pegged = hpas.filter(
            (h: { current_replicas: number; max_replicas: number }) =>
                h.current_replicas >= h.max_replicas && h.max_replicas > 0
        )
        if (pegged.length > 0) {
            const names: string = pegged.map((h: { name: string }) => `**${h.name}**`).join(', ')
            issues.push(`${pegged.length} HPA(s) at max capacity: ${names}`)
        }

        // Check for HPAs with minReplicas=1 (no HA)
        const low_min = hpas.filter(
            (h: { min_replicas: number }) => h.min_replicas < 2
        )
        if (low_min.length > 0) {
            const names: string = low_min.map((h: { name: string }) => `**${h.name}**`).join(', ')
            issues.push(`${low_min.length} HPA(s) with minReplicas < 2: ${names}`)
        }

        if (issues.length > 0) {
            return {
                status: 'warning',
                status_reason: '{{hpa_count}} HPA(s) configured with issues: {{{issues}}}.',
                fix_hint: `Review HPA configuration:\n\`\`\`\nkubectl get hpa -n ${ns}\nkubectl describe hpa -n ${ns}\n\`\`\`\n` +
                    'For services at max capacity, increase maxReplicas or add more nodes.\n' +
                    'For HA, set minReplicas >= 2.',
                display_value: `${hpa_count} HPAs, ${issues.length} issue(s)`,
                raw_output: point.raw_output,
                template_data: { hpa_count, issues: issues.join('; ') },
            }
        }

        return {
            status: 'healthy',
            status_reason: '{{hpa_count}} HPA(s) configured and operating normally.',
            display_value: `${hpa_count} HPAs`,
            raw_output: point.raw_output,
            template_data: { hpa_count },
        }
    }
}

export default HpaConfigurationChecker
