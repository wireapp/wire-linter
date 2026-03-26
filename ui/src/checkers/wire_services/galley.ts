/**
 * Checks Galley (conversations) service health and replica count.
 *
 * Pulls two targets: wire_services/galley/healthy (boolean) and
 * wire_services/galley/replicas (number). Combines them into a single
 * verdict the service needs to be healthy AND have enough replicas
 * to handle traffic reliably.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class GalleyChecker extends BaseChecker {
    readonly path: string = 'wire_services/galley'
    readonly name: string = 'Galley (conversations), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Galley** service (conversations, teams, and messaging logic) is running with enough replicas. If Galley is down, users cannot send messages, create conversations, or manage teams.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/galley/healthy')
        const replicas_point = data.get('wire_services/galley/replicas')

        // No data from either target
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Galley health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `galley` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Galley health and replica checks',
                recommendation: 'Galley (conversations), healthy + replica count data not collected.',
            }
        }

        // Put the raw data together so you can see what we found
        const combined_raw: string = [healthy_point?.raw_output, replicas_point?.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        // Health probe ran but returned no result
        if (healthy_point && healthy_point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Galley health probe returned no result.',
                recommendation: 'Galley health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service went down or we're missing health data
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Galley service is down or health data is missing.',
                recommendation: 'Galley (conversations) is down. Check pod logs with <command>kubectl logs -l app=galley</command>.',
                raw_output: combined_raw,
            }
        }

        const raw_replicas = replicas_point?.value
        const replicas: number = (typeof raw_replicas === 'number' && !isNaN(raw_replicas)) ? raw_replicas : 0

        // Not running any copies
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Galley has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment galley -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=galley`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Galley (conversations) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Just one replica is risky
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Galley has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment galley -n wire --replicas=3`\n2. Or update the Helm values to set `galley.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=galley -o wide`',
                recommendation: `Galley (conversations) has only ${replicas} replica. Scale to 3 for high availability.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Galley is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default GalleyChecker
