/**
 * Checks Spar (SSO/SCIM) health and replica count.
 *
 * Grabs both the healthy status and replica count, then makes sure
 * the service is actually up and has enough replicas for redundancy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, parse_number, type DataLookup } from '../data_lookup'

export class SparChecker extends BaseChecker {
    readonly path: string = 'wire_services/spar'
    readonly name: string = 'Spar (SSO/SCIM), healthy + replica count'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **Spar** service (SAML SSO and SCIM provisioning) is running with enough replicas. If Spar is down, enterprise users cannot log in via SSO and automated user provisioning stops working.'

    check(data: DataLookup): CheckResult {
        const healthy_point = data.get('wire_services/spar/healthy')
        const replicas_point = data.get('wire_services/spar/replicas')

        // Didn't get data from either source
        if (!healthy_point && !replicas_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Spar health and replica count data was not collected.',
                fix_hint: '1. Verify the gatherer script ran with Wire service targets enabled\n2. Check that the `spar` target is not excluded in the gatherer config\n3. Review the gatherer logs for errors during the Spar health and replica checks',
                recommendation: 'Spar (SSO/SCIM), healthy + replica count data not collected.',
            }
        }

        // Combine output from both sources
        const combined_raw: string = [healthy_point?.raw_output, replicas_point?.raw_output]
            .filter(Boolean)
            .join('\n---\n')

        // Health probe ran but returned no result
        if (healthy_point && healthy_point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Spar health probe returned no result.',
                recommendation: 'Spar health target ran but produced no value. Re-run the gatherer or check target logs.',
                raw_output: combined_raw,
            }
        }

        // Service is down or we don't have data
        if (!healthy_point || coerce_boolean(healthy_point.value) === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Spar service is **down** or health data is missing.',
                fix_hint: '1. Check pod status: `kubectl get pods -n wire -l app=spar`\n2. View pod logs: `kubectl logs -n wire -l app=spar --tail=100`\n3. Describe the deployment: `kubectl describe deployment spar -n wire`\n4. Verify Spar can connect to Cassandra and the SAML IdP\n5. Check for certificate or secret mounting issues: `kubectl describe pod -n wire -l app=spar`',
                recommendation: 'Spar (SSO/SCIM) is down. Check pod logs with <command>kubectl logs -l app=spar</command>.',
                raw_output: combined_raw,
            }
        }

        const replicas: number = replicas_point ? (parse_number(replicas_point) ?? 0) : 0

        // No replicas running at all
        if (!replicas_point || replicas < 1) {
            return {
                status: 'unhealthy',
                status_reason: 'Spar has **{{replicas}}** running replicas.',
                fix_hint: '1. Check deployment status: `kubectl get deployment spar -n wire`\n2. Look for failed pods: `kubectl get pods -n wire -l app=spar`\n3. Check events for scheduling failures: `kubectl get events -n wire --field-selector involvedObject.kind=Pod`\n4. Verify resource quotas are not exceeded: `kubectl describe resourcequota -n wire`',
                recommendation: 'Spar (SSO/SCIM) has no running replicas.',
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // Only one replica that's a single point of failure
        if (replicas < 2) {
            return {
                status: 'warning',
                status_reason: 'Spar has only **{{replicas}}** replica, which is a single point of failure.',
                fix_hint: '1. Scale up the deployment: `kubectl scale deployment spar -n wire --replicas=3`\n2. Or update the Helm values to set `spar.replicaCount: 3` and run `helm upgrade`\n3. Verify pods are running across different nodes: `kubectl get pods -n wire -l app=spar -o wide`',
                recommendation: `Spar (SSO/SCIM) has only ${replicas} replica. Scale to at least 2 for redundancy.`,
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        // 2 replicas is decent but not ideal for full HA
        if (replicas === 2) {
            return {
                status: 'healthy',
                status_reason: 'Spar is running with **{{replicas}}** replicas.',
                recommendation: 'Spar (SSO/SCIM) has 2 replicas. Consider scaling to 3 for full high availability.',
                display_value: `${replicas} replicas`,
                raw_output: combined_raw,
                template_data: { replicas },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Spar is running with **{{replicas}}** healthy replicas.',
            display_value: `${replicas} replicas`,
            raw_output: combined_raw,
            template_data: { replicas },
        }
    }
}

export default SparChecker
