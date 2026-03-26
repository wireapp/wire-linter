/**
 * Flags pods stuck in Pending state (scheduling failures).
 *
 * Pending pods never started — usually because of insufficient
 * resources, unsatisfiable node affinity, or missing PVCs.
 *
 * Consumes: kubernetes/pods/scheduling_failures
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class SchedulingFailuresChecker extends BaseChecker {
    readonly path: string = 'kubernetes/scheduling_failures'
    readonly name: string = 'Pod scheduling failures'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly data_path: string = 'kubernetes/pods/scheduling_failures'
    readonly explanation: string =
        'Pods stuck in **Pending** state never started at all. This usually means ' +
        'insufficient CPU/memory resources, unsatisfiable node affinity rules, ' +
        'missing PersistentVolumeClaims, or taints without matching tolerations.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const point = data.get('kubernetes/pods/scheduling_failures')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Scheduling failure data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            pending_count?: number
            pending_pods?: { name: string; namespace: string; conditions: { type: string; reason: string; message: string }[] }[]
            scheduling_events?: { pod: string; reason: string; message: string; count: number }[]
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse scheduling data.' }
        }

        // Guard against null/primitive results (e.g. point.value was null → JSON.parse("null") → null)
        if (parsed === null || typeof parsed !== 'object') {
            return { status: 'gather_failure', status_reason: 'Scheduling data is not a valid object.' }
        }

        const pending_count: number = parsed.pending_count ?? 0

        if (pending_count === 0) {
            return {
                status: 'healthy',
                status_reason: 'No pods stuck in Pending state.',
                display_value: '0 pending',
                template_data: { pending_count: 0, pod_details: '' },
            }
        }

        // Build details from pending pods and events
        const pod_details: string = (parsed.pending_pods ?? [])
            .slice(0, 10)
            .map((p: { name: string; namespace: string }) => `\`${p.namespace}/${p.name}\``)
            .join(', ')

        const event_details: string = (parsed.scheduling_events ?? [])
            .slice(0, 5)
            .map((e: { pod: string; reason: string; message: string }) =>
                `- **${e.pod}**: ${e.message.slice(0, 200)}`)
            .join('\n')

        return {
            status: 'unhealthy',
            status_reason: `**{{pending_count}}** pod(s) stuck in Pending state: {{{pod_details}}}.`,
            fix_hint: `1. Check pod events for details:\n   \`\`\`\n   kubectl describe pod <pod-name> -n ${ns}\n   \`\`\`\n` +
                '2. Common causes:\n   - Insufficient CPU/memory: scale up nodes or reduce resource requests\n' +
                '   - Missing PVC: create the required PersistentVolumeClaim\n' +
                '   - Node affinity: check node labels match pod affinity rules\n' +
                '   - Taints: add tolerations to the deployment',
            recommendation: pod_details || event_details
                ? (pod_details ? `Pending pods: ${pod_details}\n\n` : '') +
                  (event_details ? `Scheduling events:\n${event_details}` : '')
                : undefined,
            display_value: `${pending_count} pending`,
            raw_output: point.raw_output,
            template_data: { pending_count, pod_details },
        }
    }
}

export default SchedulingFailuresChecker
