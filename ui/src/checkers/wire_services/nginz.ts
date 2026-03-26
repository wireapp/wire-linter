/**
 * Checks Nginz (API gateway) service health and replica count.
 *
 * Looks at two things: whether the service is healthy and how many replicas
 * it's got running. Both need to be good.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class NginzChecker extends BaseChecker {
    readonly path: string = 'wire_services/nginz'
    readonly name: string = 'Nginz (API gateway), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Nginz** API gateway is running with enough replicas. Nginz is the reverse proxy that routes all client API traffic to backend services, so if it is down, the entire Wire API becomes unreachable.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/nginz/healthy')
        const replicas_point = data.get('wire_services/nginz/replicas')

        // Didn't get data for either target
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Nginz health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `nginz` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Nginz health and replica checks',
                recommendation: 'Nginz (API gateway), healthy + replica count data not collected.',
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
                status_reason: 'Nginz health probe returned no result.',
                recommendation: 'Nginz health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service is down or we didn't get health data
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Nginz API gateway is down or health data is missing.',
                recommendation: 'Nginz (API gateway) is down. Check pod logs with <command>kubectl logs -l app=nginz</command>.',
                raw_output: combined_raw,
            }
        }

        const raw_replicas = replicas_point?.value
        const replicas: number = (typeof raw_replicas === 'number' && !isNaN(raw_replicas)) ? raw_replicas : 0

        // No replicas running or no data on replica count
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Nginz has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment nginz -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=nginz`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Nginz (API gateway) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Only 1 replica need at least 2
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Nginz has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment nginz -n wire --replicas=3`\n2. Or update the Helm values to set `nginz.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=nginz -o wide`',
                recommendation: `Nginz (API gateway) has only ${replicas} replica. Scale to 3 for high availability.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Nginz is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default NginzChecker
