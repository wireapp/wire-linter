/**
 * Checks asset host HTTP service availability.
 *
 * Consumes ONE target: wire_services/asset_host (boolean or string).
 * The asset host serves static assets for the webapp and this linter
 * tool itself, so if it's down, neither is reachable.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class AssetHostChecker extends BaseChecker {
    readonly path: string = 'wire_services/asset_host'
    readonly name: string = 'Asset host HTTP service running'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Verifies the **asset host** HTTP service is reachable. It serves static assets for the webapp and uploaded files -- if it is down, the web client fails to load and file downloads break.'

    check(data: DataLookup): CheckResult {
        const point = data.get_applicable('wire_services/asset_host') ?? data.get('direct/wire_services/asset_host')

        // No data collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Asset host HTTP service data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `asset_host` target is not excluded in the gatherer config\n3. Review the gatherer logs for connection errors or timeouts when probing the asset host',
                recommendation: 'Asset host HTTP service running data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Asset host data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Asset host target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const value: boolean | string | number = point.value
        // Build a recommendation that includes the health assessment from the collector
        const health_detail: string = point.metadata?.health_info ?? ''
        const base_recommendation: string = 'Asset host service is down. The webapp and this linter tool itself are unreachable.'
        const recommendation: string = health_detail
            ? `${base_recommendation} ${health_detail}.`
            : base_recommendation

        // false means the service is down
        if (value === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Asset host HTTP service is **not reachable**.',
                fix_hint: '1. Check if the asset host pod is running: `kubectl get pods -n wire -l app=assets`\n2. Verify the service endpoint: `kubectl get svc -n wire | grep asset`\n3. Test connectivity from within the cluster: `kubectl exec -n wire <any-pod> -- curl -sI http://assets`\n4. Check ingress rules: `kubectl get ingress -n wire -o yaml | grep asset`\n5. Review pod logs for errors: `kubectl logs -n wire -l app=assets --tail=100`',
                recommendation,
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // true or any truthy value means it's running
        return {
            status: 'healthy',
            status_reason: 'Asset host HTTP service is running and **reachable**.',
            display_value: value,
            raw_output: point.raw_output,
        }
    }
}

export default AssetHostChecker
