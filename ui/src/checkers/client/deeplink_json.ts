/**
 * Client-mode checker: deeplink.json availability and validity.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientDeeplinkJsonChecker extends BaseChecker {
    readonly path: string = 'client/deeplink_json'
    readonly name: string = 'Deeplink.json (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies the deeplink.json file is available and valid from this client network. Mobile clients use it to auto-discover backend settings.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_deeplink) {
            return { status: 'not_applicable', status_reason: 'Deeplink is not enabled.' }
        }

        const point = data.get('client/http/deeplink_json')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Deeplink.json data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const reachable: boolean = parsed.reachable as boolean ?? false
        const valid_json: boolean = parsed.valid_json as boolean ?? false

        if (valid_json) {
            const fields: Record<string, unknown> = (parsed.fields as Record<string, unknown>) ?? {}
            const field_count: number = Object.keys(fields).length
            return { status: 'healthy', status_reason: `Deeplink.json is valid and contains **${field_count}** configuration field(s).`, display_value: `valid (${field_count} fields)`, raw_output: point.raw_output }
        }

        if (reachable) {
            return { status: 'warning', status_reason: 'Deeplink.json is reachable but contains **invalid JSON**. Mobile clients will not auto-discover backend settings.', display_value: 'invalid JSON', raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: 'Deeplink.json **not reachable** from this network. Mobile clients will not auto-discover backend settings.',
            display_value: 'not reachable',
            raw_output: point.raw_output,
        }
    }
}

export default ClientDeeplinkJsonChecker
