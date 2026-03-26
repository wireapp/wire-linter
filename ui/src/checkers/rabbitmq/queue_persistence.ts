/**
 * Makes sure all RabbitMQ queues are durable, otherwise they poof on restart.
 *
 * Reads databases/rabbitmq/queue_persistence (count of non-durable queues).
 * Non-durable queues vanish when RabbitMQ restarts, silently killing Wire
 * notifications and calls. See WPB-17723.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class RabbitmqQueuePersistenceChecker extends BaseChecker {
    readonly path: string = 'rabbitmq/queue_persistence'
    readonly name: string = 'RabbitMQ queue durability (see: WPB-17723)'
    readonly category: string = 'Data / RabbitMQ'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Checks that all RabbitMQ queues are declared as **durable**. Non-durable queues vanish on RabbitMQ restart, silently breaking Wire **notifications** and **call signaling**.'

    check(data: DataLookup): CheckResult {
        // RabbitMQ is more critical when federation is enabled (async event processing).
        // Without federation, downgrade failures from unhealthy to warning.
        const rmq_failure_severity: 'unhealthy' | 'warning' = (
            data.config?.options?.expect_federation ? 'unhealthy' : 'warning'
        )

        const point = data.get_applicable('databases/rabbitmq/queue_persistence') ?? data.get('direct/rabbitmq/queue_persistence')

        // We didn't get the data back
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ queue durability data was not collected.',
                fix_hint: '1. Verify connectivity to the RabbitMQ node\n2. Check that `rabbitmqctl list_queues name durable` runs successfully\n3. If using the management API: `curl -u guest:guest http://<host>:15672/api/queues`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Couldn\'t collect RabbitMQ queue durability data.',
            }
        }

        const non_durable_count = parse_number(point)

        // Value couldn't be parsed as a number (null, string mismatch, or gatherer error)
        if (non_durable_count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ queue durability value could not be parsed as a number.',
                recommendation: point.metadata?.error ?? 'The gathered queue durability data was not in a recognized numeric format.',
                raw_output: point.raw_output,
            }
        }

        // All good everything is durable
        if (non_durable_count === 0) {
            return {
                status: 'healthy',
                status_reason: 'All RabbitMQ queues are declared as **durable**.',
                display_value: 'all durable',
                raw_output: point.raw_output,
            }
        }

        // Got non-durable queues those will vanish when RabbitMQ restarts
        return {
            status: rmq_failure_severity,
            status_reason: '**{{non_durable_count}}** RabbitMQ queue(s) are **non-durable** and will be lost on restart.',
            fix_hint: '1. List non-durable queues: `rabbitmqctl list_queues name durable | grep false`\n2. For each non-durable queue, note its consumers and bindings\n3. Delete the non-durable queue: `rabbitmqctl delete_queue <queue_name>`\n4. Re-declare it with `durable=true` from the consuming application\n5. Verify durability: `rabbitmqctl list_queues name durable` should show `true` for all queues\n6. See **WPB-17723** for the full context on this issue',
            recommendation: `${non_durable_count} RabbitMQ queue(s) aren't durable. They'll get deleted on restart and you'll lose notifications and call events silently. Delete those queues and redeclare them with durable=true.`,
            display_value: non_durable_count,
            display_unit: 'non-durable',
            raw_output: point.raw_output,
            template_data: { non_durable_count },
        }
    }
}

export default RabbitmqQueuePersistenceChecker
