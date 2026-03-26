/**
 * Checks the RabbitMQ cluster status.
 *
 * Consumes the databases/rabbitmq/cluster_status target (a string).
 * If it's not «healthy», the cluster's borked and messages won't route right.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClusterStatusChecker extends BaseChecker {
    readonly path: string = 'rabbitmq/cluster_status'
    readonly name: string = 'Cluster status'
    readonly category: string = 'Data / RabbitMQ'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies the **RabbitMQ cluster** is in a healthy state. An unhealthy cluster prevents message routing between Wire backend services, breaking **notifications**, **calls**, and **message delivery**.'

    check(data: DataLookup): CheckResult {
        // RabbitMQ is more critical when federation is enabled (async event processing).
        // Without federation, downgrade failures from unhealthy to warning.
        const rmq_failure_severity: 'unhealthy' | 'warning' = (
            data.config?.options?.expect_federation ? 'unhealthy' : 'warning'
        )

        const point = data.get_applicable('databases/rabbitmq/cluster_status') ?? data.get('direct/rabbitmq/cluster_status')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ cluster status data was not collected.',
                fix_hint: '1. Verify connectivity to the RabbitMQ node\n2. Check that `rabbitmqctl cluster_status` runs successfully\n3. If using the management API, verify it is enabled: `curl -u guest:guest http://<host>:15672/api/healthchecks/node`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Cluster status data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ cluster status data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Cluster status target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string = point.value as string

        // If it's not «healthy», something's wrong
        if (val !== 'healthy') {
            return {
                status: rmq_failure_severity,
                status_reason: 'RabbitMQ cluster status is **{{cluster_status}}** instead of the expected **healthy**.',
                fix_hint: '1. Check cluster status: `rabbitmqctl cluster_status`\n2. Check node health: `rabbitmqctl node_health_check`\n3. Inspect logs: `journalctl -u rabbitmq-server` or `kubectl logs <rabbitmq_pod>`\n4. Verify all nodes can reach each other: `rabbitmqctl cluster_status` should list all expected nodes\n5. If a node is down, restart it: `systemctl restart rabbitmq-server` or `kubectl delete pod <rabbitmq_pod>`',
                recommendation: 'RabbitMQ cluster is not healthy. Check rabbitmqctl cluster_status for details.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { cluster_status: val },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'RabbitMQ cluster is reporting a **healthy** status.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default ClusterStatusChecker
