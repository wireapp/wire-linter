/**
 * Checks Gundeck (push notifications) service health and replica count.
 *
 * Looks at two things: whether the service is healthy and how many replicas
 * it's got running. If it's not healthy or doesn't have enough replicas for
 * redundancy, you've got a problem.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class GundeckChecker extends BaseChecker {
    readonly path: string = 'wire_services/gundeck'
    readonly name: string = 'Gundeck (push notifications), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Gundeck** service (push notifications) is running with enough replicas. If Gundeck is down, mobile and desktop clients stop receiving push notifications for new messages and calls.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/gundeck/healthy')
        const replicas_point = data.get('wire_services/gundeck/replicas')

        // Didn't get data for either target
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Gundeck health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `gundeck` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Gundeck health and replica checks',
                recommendation: 'Gundeck (push notifications), healthy + replica count data not collected.',
            }
        }

        // Combine raw output from both data points
        const combined_raw: string = [healthy_point?.raw_output, replicas_point?.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        // Health probe ran but returned no result
        if (healthy_point && healthy_point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Gundeck health probe returned no result.',
                recommendation: 'Gundeck health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service is down or we didn't get health data
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Gundeck service is down or health data is missing.',
                recommendation: 'Gundeck (push notifications) is down. Check pod logs with <command>kubectl logs -l app=gundeck</command>.',
                raw_output: combined_raw,
            }
        }

        const raw_replicas = replicas_point?.value
        const replicas: number = (typeof raw_replicas === 'number' && !isNaN(raw_replicas)) ? raw_replicas : 0

        // No replicas running or no data on replica count
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Gundeck has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment gundeck -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=gundeck`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Gundeck (push notifications) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Only 1 replica that's a single point of failure
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Gundeck has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment gundeck -n wire --replicas=3`\n2. Or update the Helm values to set `gundeck.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=gundeck -o wide`',
                recommendation: `Gundeck (push notifications) has only ${replicas} replica. Scale to at least 2 for redundancy.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // 2 replicas is ok but we'd like 3 for better redundancy
        if (replicas === 2) {
            return {
                status: 'healthy',
                status_reason: 'Gundeck is running with **{{replicas}}** replicas.',
                recommendation: 'Gundeck (push notifications) has 2 replicas. Consider scaling to 3 for full high availability.',
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Gundeck is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default GundeckChecker
