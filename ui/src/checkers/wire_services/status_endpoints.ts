/**
 * Checks Wire service /i/status endpoint responsiveness.
 *
 * The /i/status endpoints are how we know if Wire services are actually alive.
 * If they're not responding, the service is down.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class StatusEndpointsChecker extends BaseChecker {
    readonly path: string = 'wire_services/status_endpoints'
    readonly name: string = 'Wire service /i/status endpoints'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Probes the internal `/i/status` health endpoints of all Wire backend services. If a service stops responding to its status endpoint, it is either crashed or stuck and needs investigation.'

    check(data: DataLookup): CheckResult {
        // Try the SSH-gathered path first, fall back to the direct/kubernetes path
        const point = data.get_applicable('wire_services/status_endpoints') ?? data.get('direct/wire_services/status_endpoints')

        // Didn't collect data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Wire service `/i/status` endpoints data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `status_endpoints` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the `/i/status` endpoint checks',
                recommendation: 'Wire service /i/status endpoints data not collected.',
            }
        }

        // Collection ran but failed (Python collector sets value=null on error)
        if (point.value === null) {
            // Use the actual error message from the collector when available
            const error_detail: string = point.metadata?.error
                ?? 'Wire service /i/status endpoints could not be checked.'

            return {
                status: 'unhealthy',
                status_reason: 'Status endpoint check returned no value: **{{error_detail}}**',
                fix_hint: '1. Check if Wire pods are running: `kubectl get pods -n wire`\n2. Test individual status endpoints from within the cluster:\n   - `kubectl exec -n wire <any-pod> -- curl -s http://brig:8080/i/status`\n   - `kubectl exec -n wire <any-pod> -- curl -s http://galley:8080/i/status`\n3. Check network policies that might block internal traffic: `kubectl get networkpolicy -n wire`',
                recommendation: error_detail,
                raw_output: point.raw_output,
                template_data: { error_detail },
            }
        }

        // Narrowed to non-null after the guard above
        const value: boolean | string | number = point.value

        // Endpoints are down — coerce_boolean handles string "false" → boolean false,
        // and we also catch numeric 0 and empty string which indicate no endpoints responding
        if (coerce_boolean(value) === false || value === 0 || value === '') {
            return {
                status: 'unhealthy',
                status_reason: 'One or more Wire service `/i/status` endpoints are **not responding**.',
                fix_hint: '1. Check which services are down: `kubectl get pods -n wire`\n2. Test each service endpoint individually:\n   - `kubectl exec -n wire <any-pod> -- curl -s http://brig:8080/i/status`\n   - `kubectl exec -n wire <any-pod> -- curl -s http://galley:8080/i/status`\n   - `kubectl exec -n wire <any-pod> -- curl -s http://cannon:8080/i/status`\n3. Check pod logs for crashed services: `kubectl logs -n wire <pod-name> --tail=100`\n4. Look for OOM kills or crash loops in events: `kubectl get events -n wire --sort-by=.lastTimestamp`',
                recommendation: point.metadata?.health_info
                    ?? 'Some Wire service /i/status endpoints are not responding.',
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // Endpoints are up (value is like "6/6 responding")
        return {
            status: 'healthy',
            status_reason: 'All Wire service `/i/status` endpoints are responding (**{{endpoint_status}}**).',
            display_value: value,
            raw_output: point.raw_output,
            template_data: { endpoint_status: value },
        }
    }
}

export default StatusEndpointsChecker
