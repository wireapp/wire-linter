/**
 * Detects Deployments stuck mid-rollout.
 *
 * A botched helm upgrade (bad image, crashing init container) leaves
 * the deployment half-rolled-out indefinitely — old and new pods running
 * simultaneously with potentially incompatible code.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

interface StuckService {
    service: string
    replicas: number
    ready: number
    updated: number
    unavailable: number
    reason: string
}

export class StuckRolloutsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/stuck_rollouts'
    readonly name: string = 'Stuck rollouts'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string =
        'Detects Deployments stuck mid-rollout. A botched `helm upgrade` (bad image, ' +
        'crashing init container) leaves old and new pods running simultaneously. ' +
        'The deployment never completes, and the service runs in a degraded mixed state.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const stuck: StuckService[] = []
        let services_checked: number = 0

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            let details: {
                replicas?: number
                ready_replicas?: number
                updated_replicas?: number
                unavailable_replicas?: number
                available_replicas?: number
                conditions?: { type: string; status: string; reason: string; message: string }[]
            }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            const replicas: number = details.replicas ?? 0
            const ready: number = details.ready_replicas ?? 0
            const updated: number = details.updated_replicas ?? 0
            const unavailable: number = details.unavailable_replicas ?? 0

            // Collect individual signals — each is expected transiently during a normal rolling update,
            // so a single signal alone is not enough to declare the rollout stuck
            const is_partial_rollout: boolean = replicas > 0 && updated < replicas
            const has_unavailable: boolean = unavailable > 0

            const progressing = (details.conditions ?? []).find(
                (c: { type: string }) => c.type === 'Progressing'
            )
            const is_timed_out: boolean = progressing?.status === 'False'

            // Require the Progressing=False timeout plus at least one corroborating symptom to flag
            // a stuck rollout. Partial rollout + unavailable pods alone are expected transient states
            // during a healthy rolling update and must not trigger a false positive.
            const is_stuck: boolean = is_timed_out && (is_partial_rollout || has_unavailable)

            // Build human-readable reasons for whichever signals are active
            const reasons: string[] = []
            if (is_partial_rollout) reasons.push(`only ${updated}/${replicas} updated`)
            if (has_unavailable) reasons.push(`${unavailable} unavailable`)
            if (is_timed_out) reasons.push(`rollout timed out: ${progressing!.reason}`)

            if (is_stuck) {
                stuck.push({
                    service,
                    replicas,
                    ready,
                    updated,
                    unavailable,
                    reason: reasons.join('; '),
                })
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment details data collected.',
                fix_hint: 'Ensure the gatherer has kubectl access and re-run.',
            }
        }

        if (stuck.length > 0) {
            const details: string = stuck
                .map((s: StuckService) => `**${s.service}**: ${s.reason} (${s.ready}/${s.replicas} ready)`)
                .join('\n- ')

            const rollback_commands: string = stuck
                .map((s: StuckService) => `kubectl rollout undo deployment/${s.service} -n ${ns}`)
                .join('\n')

            return {
                status: 'unhealthy',
                status_reason: `{{stuck_count}} service(s) have stuck or incomplete rollouts.`,
                fix_hint: 'Investigate the failing pods:\n```\n{{#each stuck_services}}kubectl describe deployment/{{this}} -n {{../ns}}\n{{/each}}```\n\n' +
                    'To rollback:\n```\n{{{rollback_commands}}}\n```',
                recommendation: `Stuck rollouts:\n- ${details}`,
                display_value: `${stuck.length} stuck`,
                template_data: {
                    stuck_count: stuck.length,
                    stuck_services: stuck.map((s: StuckService) => s.service),
                    rollback_commands,
                    ns,
                },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All ${services_checked} service(s) fully rolled out.`,
            display_value: `${services_checked} OK`,
            template_data: { stuck_count: 0, stuck_services: [], rollback_commands: '' },
        }
    }
}

export default StuckRolloutsChecker
