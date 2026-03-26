/**
 * Checks if Brig (user accounts service) is healthy and has enough replicas running.
 *
 * Uses two data points: wire_services/brig/healthy (yes/no) and
 * wire_services/brig/replicas (count). Both need to pass: service must be up
 * AND we need at least a couple replicas for safety.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class BrigChecker extends BaseChecker {
    readonly path: string = 'wire_services/brig'
    readonly name: string = 'Brig (user accounts), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Brig** service (user accounts and authentication) is running with enough replicas. If Brig is down, users cannot log in, register, or manage their accounts.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/brig/healthy')
        const replicas_point = data.get('wire_services/brig/replicas')

        // No data coming in at all
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Brig health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `brig` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Brig health and replica checks',
                recommendation: 'Brig (user accounts), healthy + replica count data not collected.',
            }
        }

        // Combine the raw output so we can see both pieces of data
        const combined_raw: string = [healthy_point?.raw_output, replicas_point?.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        // Health probe ran but returned no result
        if (healthy_point && healthy_point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Brig health probe returned no result.',
                recommendation: 'Brig health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service is not there or we don't have health data
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Brig service is down or health data is missing.',
                recommendation: 'Brig (user accounts) is down. Check pod logs with <command>kubectl logs -l app=brig</command>.',
                raw_output: combined_raw,
            }
        }

        const raw_replicas = replicas_point?.value
        const replicas: number = (typeof raw_replicas === 'number' && !isNaN(raw_replicas)) ? raw_replicas : 0

        // No replicas running at all
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Brig has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment brig -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=brig`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Brig (user accounts) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Only one replica is risky
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Brig has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment brig -n wire --replicas=3`\n2. Or update the Helm values to set `brig.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=brig -o wide`',
                recommendation: `Brig (user accounts) has only ${replicas} replica. Scale to 3 for safety.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Brig is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default BrigChecker
