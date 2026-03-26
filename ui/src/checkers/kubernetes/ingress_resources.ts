/**
 * Shows what ingress resources are set up in the cluster.
 *
 * Gets the data from kubernetes/ingress/list and displays it. Nothing to validate here,
 * just reporting what exists.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class IngressResourcesChecker extends BaseChecker {
    readonly path: string = 'kubernetes/ingress_resources'
    readonly name: string = 'Ingress resources'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports the **ingress resources** configured in the cluster. Provides visibility into how external traffic is routed to Wire services, useful for diagnosing DNS or routing issues.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/ingress/list')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Ingress resources data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/ingress/list\n   ```\n3. Manually check: `kubectl get ingress -A`',
                recommendation: 'Ingress resources data not collected.',
            }
        }

        // Value was null — target ran but produced no result
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Ingress resources data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Ingress resources target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const value: string | number = point.value as string | number

        return {
            status: 'healthy',
            status_reason: 'Ingress resources have been collected successfully.',
            display_value: value,
            raw_output: point.raw_output,
        }
    }
}

export default IngressResourcesChecker
