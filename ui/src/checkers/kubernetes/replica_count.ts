/**
 * Warns when core services run with a single replica.
 *
 * A service with replicas=1 is a single point of failure — any pod
 * restart, node failure, or deployment update causes a complete outage.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

export class ReplicaCountChecker extends BaseChecker {
    readonly path: string = 'kubernetes/replica_count'
    readonly name: string = 'Replica count'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string =
        'A service with **replicas=1** is a single point of failure. Any pod restart, ' +
        'node failure, or deployment update causes a complete outage for that service. ' +
        'Production deployments should have at least 2 replicas for high availability.'

    check(data: DataLookup): CheckResult {
        const single_replica: string[] = []
        let services_checked: number = 0
        const raw_outputs: string[] = []

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            if (point.raw_output) raw_outputs.push(point.raw_output)

            let details: { replicas?: number }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            const replicas: number = details.replicas ?? 0
            if (replicas < 2) {
                single_replica.push(service)
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment details data collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        if (single_replica.length > 0) {
            const names: string = single_replica.map((s: string) => `**${s}**`).join(', ')

            return {
                status: 'warning',
                status_reason: `{{count}} service(s) running with a single replica: {{{names}}}.`,
                fix_hint: 'Increase replicas in your Helm values:\n```yaml\nbrig:\n  replicaCount: 2\n```\nThen run `helm upgrade` to apply.',
                display_value: `${single_replica.length} single-replica`,
                raw_output: raw_outputs.join('\n') || undefined,
                template_data: { count: single_replica.length, names },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All ${services_checked} service(s) have 2+ replicas for high availability.`,
            display_value: `${services_checked} OK`,
            raw_output: raw_outputs.join('\n') || undefined,
            template_data: { count: 0, names: '' },
        }
    }
}

export default ReplicaCountChecker
