/**
 * Checks Cargohold (asset storage) service health and replica count.
 *
 * Pulls data from two targets: wire_services/cargohold/healthy (boolean) and
 * wire_services/cargohold/replicas (number). Combines them to determine if the
 * service is running and has enough replicas for high availability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, parse_number, type DataLookup } from '../data_lookup'

export class CargoholdChecker extends BaseChecker {
    readonly path: string = 'wire_services/cargohold'
    readonly name: string = 'Cargohold (asset storage), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Cargohold** service (file and asset storage) is running with enough replicas. If Cargohold is down, users cannot upload or download files, images, or other attachments.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/cargohold/healthy')
        const replicas_point = data.get('wire_services/cargohold/replicas')

        // No data collected at all
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cargohold health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `cargohold` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Cargohold health and replica checks',
                recommendation: 'Cargohold (asset storage), healthy + replica count data not collected.',
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
                status_reason: 'Cargohold health probe returned no result.',
                recommendation: 'Cargohold health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service is down or we don't have health data
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Cargohold service is **down** or health data is missing.',
                fix_hint: '1. Check pod status: `kubectl get pods -n wire -l app=cargohold`\n2. View pod logs: `kubectl logs -n wire -l app=cargohold --tail=100`\n3. Describe the deployment: `kubectl describe deployment cargohold -n wire`\n4. Verify Cargohold can reach the S3/MinIO storage backend\n5. Check for disk pressure or storage quota issues on the nodes',
                recommendation: 'Cargohold (asset storage) is down. Check pod logs with <command>kubectl logs -l app=cargohold</command>.',
                raw_output: combined_raw,
            }
        }

        // Replica count probe ran but returned no result (gather failure, not zero replicas)
        if (replicas_point && replicas_point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cargohold replica count probe returned no result.',
                recommendation: 'Cargohold replica count target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Safely convert replicas to a number, treat missing/invalid as 0
        const replicas: number = replicas_point ? (parse_number(replicas_point) ?? 0) : 0

        // No replicas running
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Cargohold has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment cargohold -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=cargohold`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Cargohold (asset storage) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Only 1 replica is not enough for HA
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Cargohold has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment cargohold -n wire --replicas=3`\n2. Or update the Helm values to set `cargohold.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=cargohold -o wide`',
                recommendation: `Cargohold (asset storage) has only ${replicas} replica. Scale to 3 for high availability.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Cargohold is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default CargoholdChecker
