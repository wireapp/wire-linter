/**
 * Checks RabbitMQ memory/disk alarms.
 *
 * Consumes the databases/rabbitmq/alarms target can be:
 * boolean: true = no alarms, false = alarms active
 * string: «none» or empty = healthy, anything else = unhealthy
 *
 * When alarms fire, RabbitMQ stops publishers cold and all messaging halts.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class AlarmsChecker extends BaseChecker {
    readonly path: string = 'rabbitmq/alarms'
    readonly name: string = 'Memory/disk alarms'
    readonly category: string = 'Data / RabbitMQ'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Detects active RabbitMQ **memory or disk resource alarms**. When these fire, RabbitMQ blocks all publishers and **message flow** across Wire halts entirely.'

    check(data: DataLookup): CheckResult {
        // RabbitMQ is more critical when federation is enabled (async event processing).
        // Without federation, downgrade failures from unhealthy to warning.
        const rmq_failure_severity: 'unhealthy' | 'warning' = (
            data.config?.options?.expect_federation ? 'unhealthy' : 'warning'
        )

        const point = data.get_applicable('databases/rabbitmq/alarms') ?? data.get('direct/rabbitmq/alarms')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ memory/disk alarms data was not collected.',
                fix_hint: '1. Verify connectivity to the RabbitMQ node\n2. Check that `rabbitmqctl status` runs successfully and reports alarm info\n3. If using the management API: `curl -u guest:guest http://<host>:15672/api/nodes`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Memory/disk alarms data not collected.',
            }
        }

        // Data point exists but value is null — gathering command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ alarms data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Alarms target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        // Normalize string 'true'/'false' from the Python gatherer to actual booleans;
        // coerce_boolean returns the original value unchanged when it is not a boolean string,
        // so the result may also be a number if the gatherer emitted a numeric alarm count.
        const val: boolean | string | number = coerce_boolean(point.value) as boolean | string | number

        // Numeric value: 0 means no alarms, any non-zero count means alarms are active
        if (typeof val === 'number') {
            if (val !== 0) {
                return {
                    status: rmq_failure_severity,
                    status_reason: 'RabbitMQ memory/disk alarms are active — publishers are being blocked.',
                    recommendation: 'RabbitMQ memory/disk alarms are active. Publishers get blocked and everything stops.',
                    display_value: 'alarms active',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'No RabbitMQ memory or disk alarms are active.',
                display_value: 'no alarms',
                raw_output: point.raw_output,
            }
        }

        // Boolean true is no alarms, false means alarms are active
        if (typeof val === 'boolean') {
            if (!val) {
                return {
                    status: rmq_failure_severity,
                    status_reason: 'RabbitMQ **memory/disk alarms** are active — publishers are being blocked.',
                    fix_hint: '1. Check current alarms: `rabbitmqctl status | grep -A5 alarms`\n2. For **memory alarms**: check memory usage with `rabbitmqctl status | grep -A5 memory`\n3. Increase the memory watermark: `rabbitmqctl set_vm_memory_high_watermark 0.6`\n4. For **disk alarms**: check disk space with `df -h` on the RabbitMQ node\n5. Free disk space or increase the disk free limit: `rabbitmqctl set_disk_free_limit 1GB`\n6. Identify large queues consuming resources: `rabbitmqctl list_queues name messages memory`',
                    recommendation: 'RabbitMQ memory/disk alarms are active. Publishers get blocked and everything stops.',
                    display_value: 'alarms active',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'No RabbitMQ memory or disk alarms are active.',
                display_value: 'no alarms',
                raw_output: point.raw_output,
            }
        }

        // «none» or empty string means healthy
        if (val === 'none' || val === '') {
            return {
                status: 'healthy',
                status_reason: 'No RabbitMQ memory or disk alarms are active.',
                display_value: 'no alarms',
                raw_output: point.raw_output,
            }
        }

        // Any other string means alarms firing
        return {
            status: rmq_failure_severity,
            status_reason: 'RabbitMQ has active alarms: **{{alarm_details}}**.',
            fix_hint: '1. Check current alarms: `rabbitmqctl status | grep -A5 alarms`\n2. For **memory alarms**: check memory usage with `rabbitmqctl status | grep -A5 memory`\n3. Increase the memory watermark: `rabbitmqctl set_vm_memory_high_watermark 0.6`\n4. For **disk alarms**: check disk space with `df -h` on the RabbitMQ node\n5. Free disk space or increase the disk free limit: `rabbitmqctl set_disk_free_limit 1GB`\n6. Identify large queues consuming resources: `rabbitmqctl list_queues name messages memory`',
            recommendation: 'RabbitMQ memory/disk alarms are active. Publishers get blocked and everything stops.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { alarm_details: val },
        }
    }
}

export default AlarmsChecker
