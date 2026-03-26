/**
 * Detects services with all pods on a single node.
 *
 * When all pods of a multi-replica service land on the same node,
 * a single node failure takes out the entire service — no HA benefit.
 *
 * Consumes: kubernetes/pods/distribution/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

export class PodAntiAffinityChecker extends BaseChecker {
    readonly path: string = 'kubernetes/pod_anti_affinity'
    readonly name: string = 'Pod anti-affinity'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string =
        'When all pods of a service land on the **same node**, a single node failure ' +
        'takes out the entire service — multiple replicas provide no HA benefit. ' +
        'Pod anti-affinity rules spread pods across nodes.'

    check(data: DataLookup): CheckResult {
        const concentrated: string[] = []
        let services_checked: number = 0

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/pods/distribution/${service}`)
            if (!point) continue

            let parsed: { pod_count?: number; node_count?: number; all_on_single_node?: boolean }
            try { parsed = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            // Only flag services with multiple pods on a single node
            if (parsed.all_on_single_node && (parsed.pod_count ?? 0) > 1) {
                concentrated.push(service)
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No pod distribution data collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        if (concentrated.length > 0) {
            const names: string = concentrated.map((s: string) => `**${s}**`).join(', ')

            return {
                status: 'warning',
                status_reason: `{{count}} service(s) have all pods on a single node: {{{names}}}.`,
                fix_hint: 'Add pod anti-affinity to your Helm values:\n```yaml\naffinity:\n  podAntiAffinity:\n    preferredDuringSchedulingIgnoredDuringExecution:\n    - weight: 100\n      podAffinityTerm:\n        labelSelector:\n          matchLabels:\n            app: <service>\n        topologyKey: kubernetes.io/hostname\n```',
                display_value: `${concentrated.length} concentrated`,
                template_data: { count: concentrated.length, names },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All ${services_checked} multi-replica service(s) are spread across nodes.`,
            display_value: `${services_checked} OK`,
            template_data: { count: 0, names: '' },
        }
    }
}

export default PodAntiAffinityChecker
