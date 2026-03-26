/**
 * Surfaces recent Kubernetes warning events.
 *
 * Warning events catch image pull failures, OOMKilled, FailedScheduling,
 * probe failures, and mount errors that don't always show in pod status.
 *
 * Consumes: kubernetes/events/warnings
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class WarningEventsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/warning_events'
    readonly name: string = 'Warning events'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly data_path: string = 'kubernetes/events/warnings'
    readonly explanation: string =
        'Kubernetes warning events surface problems like **image pull failures**, ' +
        '**OOMKilled** containers, **FailedScheduling**, probe failures, and mount ' +
        'errors. These often explain why things are broken when pod status alone looks fine.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const point = data.get('kubernetes/events/warnings')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Warning events data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            total_warning_count?: number
            recent_warnings?: { reason: string; message: string; object_name: string; count: number }[]
            top_reasons?: Record<string, number>
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse warning events data.' }
        }

        // Guard against JSON.parse("null") returning null
        if (parsed === null || typeof parsed !== 'object') {
            return { status: 'gather_failure', status_reason: 'Warning events data is not a valid object.' }
        }

        const total: number = parsed.total_warning_count ?? 0

        if (total === 0) {
            return {
                status: 'healthy',
                status_reason: 'No warning events in the Wire namespace.',
                display_value: '0 warnings',
                raw_output: point.raw_output,
                template_data: { total: 0, top_reasons: '' },
            }
        }

        // Format top reasons
        const top_reasons: string = Object.entries(parsed.top_reasons ?? {})
            .slice(0, 5)
            .map(([reason, count]: [string, number]) => `**${reason}** (${count})`)
            .join(', ')

        // Format recent examples
        const examples: string = (parsed.recent_warnings ?? [])
            .slice(0, 5)
            .map((e: { reason: string; message: string; object_name: string }) =>
                `- **${e.reason}** on \`${e.object_name}\`: ${e.message.slice(0, 150)}`)
            .join('\n')

        return {
            status: 'warning',
            status_reason: `**{{total}}** warning event(s) found. Top reasons: {{{top_reasons}}}.`,
            fix_hint: `Review the warning events:\n\`\`\`\nkubectl get events -n ${ns} --field-selector type=Warning --sort-by=.lastTimestamp\n\`\`\`\nAddress the most frequent warnings first.`,
            recommendation: examples ? `Recent warnings:\n${examples}` : undefined,
            display_value: `${total} warning(s)`,
            raw_output: point.raw_output,
            template_data: { total, top_reasons },
        }
    }
}

export default WarningEventsChecker
