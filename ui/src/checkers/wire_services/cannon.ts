/**
 * Checks Cannon (WebSocket push) service health and replica count.
 *
 * Consumes TWO targets: wire_services/cannon/healthy (boolean) and
 * wire_services/cannon/replicas (number). Both must be good for the service
 * to be healthy. We need enough replicas running to avoid taking down the
 * service if one pod crashes.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class CannonChecker extends BaseChecker {
    readonly path: string = 'wire_services/cannon'
    readonly name: string = 'Cannon (WebSocket push), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Cannon** service (WebSocket connections for real-time push) is running with enough replicas. If Cannon is down, clients stop receiving real-time message delivery and presence updates.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/cannon/healthy')
        const replicas_point = data.get('wire_services/cannon/replicas')

        // No data from either target
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cannon health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `cannon` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Cannon health and replica checks',
                recommendation: 'Cannon (WebSocket push), healthy + replica count data not collected.',
            }
        }

        // Combine raw output from both sources
        const combined_raw: string = [healthy_point?.raw_output, replicas_point?.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        // Health probe ran but returned no result
        if (healthy_point && healthy_point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cannon health probe returned no result.',
                recommendation: 'Cannon health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service went down or we don't have health info
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Cannon service is down or health data is missing.',
                recommendation: 'Cannon (WebSocket push) is down. Check pod logs with <command>kubectl logs -l app=cannon</command>.',
                raw_output: combined_raw,
            }
        }

        const raw_replicas = replicas_point?.value
        const replicas: number = (typeof raw_replicas === 'number' && !isNaN(raw_replicas)) ? raw_replicas : 0

        // Not enough copies running
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Cannon has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment cannon -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=cannon`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Cannon (WebSocket push) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Too fragile with just one copy
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Cannon has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment cannon -n wire --replicas=3`\n2. Or update the Helm values to set `cannon.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=cannon -o wide`',
                recommendation: `Cannon (WebSocket push) has only ${replicas} replica. Need at least 2 so it survives a pod restart.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // 2 is okay but 3 is safer
        if (replicas === 2) {
            return {
                status: 'healthy',
                status_reason: 'Cannon is running with **{{replicas}}** replicas.',
                recommendation: 'Cannon (WebSocket push) has 2 replicas. 3 would be better for safety.',
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Cannon is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default CannonChecker
