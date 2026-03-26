/**
 * Checks CoreDNS pod health.
 *
 * DNS failures cascade to every service — if CoreDNS is down, nothing
 * works but the symptoms look like random application failures.
 *
 * Consumes: kubernetes/pods/coredns_health
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { type DataLookup, parse_json_value } from '../data_lookup'

export class CoreDnsHealthChecker extends BaseChecker {
    readonly path: string = 'kubernetes/coredns_health'
    readonly name: string = 'CoreDNS health'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly data_path: string = 'kubernetes/pods/coredns_health'
    readonly explanation: string =
        '**CoreDNS** handles all cluster DNS resolution. If CoreDNS pods are down or ' +
        'degraded, every service fails to resolve internal hostnames. The symptoms ' +
        'look like random application failures, not DNS problems.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pods/coredns_health')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'CoreDNS health data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        const parsed = parse_json_value<{
            total_pods?: number
            running_pods?: number
            ready_pods?: number
            pods?: { name: string; phase: string; ready: boolean; restarts: number }[]
        }>(point)
        if (!parsed) {
            return { status: 'gather_failure', status_reason: 'Failed to parse CoreDNS data.' }
        }

        const total: number = parsed.total_pods ?? 0
        const ready: number = parsed.ready_pods ?? 0

        if (total === 0) {
            return {
                status: 'unhealthy',
                status_reason: 'No CoreDNS pods found in kube-system. **DNS resolution is likely broken.**',
                fix_hint: '1. Check if CoreDNS is deployed:\n   ```\n   kubectl get pods -n kube-system -l k8s-app=kube-dns\n   ```\n2. Check CoreDNS deployment:\n   ```\n   kubectl get deployment coredns -n kube-system\n   ```',
                display_value: '0 pods',
                raw_output: point.raw_output,
            }
        }

        if (ready < total) {
            // Check for high restart counts
            const high_restarts = (parsed.pods ?? []).filter(
                (p: { restarts: number }) => p.restarts > 5
            )
            const restart_note: string = high_restarts.length > 0
                ? ` ${high_restarts.length} pod(s) have high restart counts (crashlooping).`
                : ''

            return {
                status: ready === 0 ? 'unhealthy' : 'warning',
                status_reason: 'Only **{{ready}}/{{total}}** CoreDNS pod(s) ready.{{{restart_note}}}',
                fix_hint: '1. Check CoreDNS pod status:\n   ```\n   kubectl get pods -n kube-system -l k8s-app=kube-dns\n   kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50\n   ```\n2. Check for resource constraints or ConfigMap issues.',
                display_value: `${ready}/${total} ready`,
                raw_output: point.raw_output,
                template_data: { ready, total, restart_note },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All {{total}} CoreDNS pod(s) healthy and ready.',
            display_value: `${total} healthy`,
            raw_output: point.raw_output,
            template_data: { total },
        }
    }
}

export default CoreDnsHealthChecker
