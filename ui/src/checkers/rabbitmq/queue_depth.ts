/**
 * Checks RabbitMQ queue depth / message backlog.
 *
 * Consumes the databases/rabbitmq/queue_depth target can be:
 * boolean: true = no backlog, false = has backlog
 * number: message count (>1000 = unhealthy, >100 = warning)
 * string: textual description
 *
 * Deep queues mean consumers are down or drowning, so messages pile up.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { is_http_error_keyword } from '../checker_helpers'

export class QueueDepthChecker extends BaseChecker {
    readonly path: string = 'rabbitmq/queue_depth'
    readonly name: string = 'Queue depth / message backlog'
    readonly category: string = 'Data / RabbitMQ'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors **RabbitMQ message backlog** depth. A growing queue means consumers are down or overwhelmed, causing delayed or lost **message delivery** across Wire services.'

    check(data: DataLookup): CheckResult {
        // RabbitMQ is more critical when federation is enabled (async event processing).
        // Without federation, downgrade failures from unhealthy to warning.
        const rmq_failure_severity: 'unhealthy' | 'warning' = (
            data.config?.options?.expect_federation ? 'unhealthy' : 'warning'
        )

        const point = data.get_applicable('databases/rabbitmq/queue_depth') ?? data.get('direct/rabbitmq/queue_depth')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ queue depth data was not collected.',
                fix_hint: '1. Verify connectivity to the RabbitMQ node\n2. Check that `rabbitmqctl list_queues name messages` runs successfully\n3. If using the management API: `curl -u guest:guest http://<host>:15672/api/queues`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Queue depth / message backlog data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ queue depth data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Queue depth target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        // Normalize string booleans so "true"/"false" reach the boolean branch below
        const raw: number | string | boolean = point.value
        const val: number | string | boolean =
            raw === 'true'  ? true  :
            raw === 'false' ? false :
            raw

        // Boolean true is no backlog
        if (typeof val === 'boolean') {
            if (val) {
                return {
                    status: 'healthy',
                    status_reason: 'RabbitMQ reports **no message backlog**.',
                    display_value: 'no backlog',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'warning',
                status_reason: 'RabbitMQ reports a message backlog is present.',
                recommendation: 'Check RabbitMQ consumers — they may be down or falling behind. Investigate queue depths with `rabbitmqctl list_queues name messages`.',
                display_value: 'backlog',
                raw_output: point.raw_output,
            }
        }

        // Numeric queue depth thresholds for severity
        if (typeof val === 'number') {
            if (val > 1000) {
                return {
                    status: rmq_failure_severity,
                    status_reason: 'RabbitMQ queue depth is **{{depth}}** messages, exceeding the **1,000** critical threshold.',
                    fix_hint: '1. Check queue depths: `rabbitmqctl list_queues name messages`\n2. Identify consumers: `rabbitmqctl list_consumers`\n3. Check if consumer services are running: `rabbitmqctl list_connections` should show active connections\n4. Inspect specific queue details via the management API: `curl -u guest:guest http://<host>:15672/api/queues/%2f/<queue_name>`\n5. For stuck queues, consider purging after confirming messages are not critical: `rabbitmqctl purge_queue <queue_name>`\n6. If consumers are overwhelmed, scale them up or investigate processing bottlenecks',
                    recommendation: `RabbitMQ has ${val} queued messages. Consumers are down or drowning.`,
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { depth: val },
                }
            }

            if (val > 100) {
                return {
                    status: 'warning',
                    status_reason: `RabbitMQ queue depth is ${val} messages, above the 100 warning threshold.`,
                    recommendation: `RabbitMQ has ${val} queued messages. Consumers may be falling behind — monitor for growth and investigate with \`rabbitmqctl list_queues name messages\`.`,
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { depth: val },
                }
            }

            return {
                status: 'healthy',
                status_reason: 'RabbitMQ queue depth is **{{depth}}** messages, within normal range.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { depth: val },
            }
        }

        // String value - check for gather-failure patterns first, then health assessment
        const lower = (val as string).toLowerCase()

        // Strings that look like collection-side failures rather than RabbitMQ queue states
        // (e.g. "timeout", "connection refused", "n/a" returned by the Python gatherer on error
        // instead of setting value: null)
        if (is_http_error_keyword(val as string) || lower === 'n/a' || lower === 'not available' || lower === 'unavailable') {
            return {
                status: 'gather_failure',
                status_reason: `RabbitMQ queue depth data could not be retrieved: "${val}".`,
                recommendation: point.metadata?.error ?? `RabbitMQ queue depth target returned an error string instead of a value.`,
                raw_output: point.raw_output,
            }
        }

        // Strings containing negative indicators are unhealthy.
        // Note: 'backlog' is intentionally absent — 'no backlog' contains it and would false-positive.
        // Instead, specific multi-word patterns like 'message backlog' and 'growing backlog' are used.
        // 'not ok' is listed explicitly before the healthy check so 'ok' word-boundary match doesn't claim it.
        const unhealthy_patterns = ['not ok', 'error', 'message backlog', 'growing backlog', 'queue backlog', 'has backlog', 'overflow', 'fail', 'overload', 'saturated']
        if (unhealthy_patterns.some(pattern => lower.includes(pattern))) {
            return {
                status: rmq_failure_severity,
                status_reason: `RabbitMQ queue depth reported an unhealthy state: "${val}".`,
                recommendation: 'RabbitMQ is reporting a queue problem. Check consumers and message backlog.',
                display_value: val as string,
                raw_output: point.raw_output,
            }
        }

        // Known-good patterns confirm no backlog.
        // Word-boundary regex prevents short tokens like 'ok' and 'none' from matching as substrings
        // of longer words (e.g. 'ok' inside 'okay', 'none' inside 'connection refused (none available)').
        const healthy_patterns: RegExp[] = [/\bok\b/, /\bnone\b/, /\bhealthy\b/, /\bempty\b/, /no backlog/, /\bclear\b/]
        if (healthy_patterns.some(pattern => pattern.test(lower))) {
            return {
                status: 'healthy',
                status_reason: `RabbitMQ queue depth reported as "${val}".`,
                display_value: val as string,
                raw_output: point.raw_output,
            }
        }

        // Unrecognized string - treat as warning since we cannot confirm health
        return {
            status: 'warning',
            status_reason: `RabbitMQ queue depth reported an unrecognized state: "${val}".`,
            display_value: val as string,
            raw_output: point.raw_output,
            template_data: { depth_value: val },
        }
    }
}

export default QueueDepthChecker
