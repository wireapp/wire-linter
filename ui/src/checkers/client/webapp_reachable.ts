/**
 * Client-mode checker: Wire webapp reachability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientWebappReachableChecker extends BaseChecker {
    readonly path: string = 'client/webapp_reachable'
    readonly name: string = 'Webapp reachable (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies that the Wire webapp is reachable via HTTPS from this client network.'

    check(data: DataLookup): CheckResult {
        const point = data.get('client/http/webapp_reachable')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Client webapp reachability data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const reachable: boolean = parsed.reachable as boolean ?? false
        const url: string = (parsed.url as string) ?? ''
        const status_code: number = (parsed.status_code as number) ?? 0
        const time_ms: number = (parsed.response_time_ms as number) ?? 0

        if (reachable) {
            return { status: 'healthy', status_reason: `Webapp reachable: \`${url}\` (HTTP ${status_code}, ${time_ms}ms).`, display_value: `reachable (${time_ms}ms)`, raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: `Cannot reach the Wire webapp at \`${url}\` from this network. Users on this network cannot use Wire in their browser.`,
            display_value: 'not reachable',
            raw_output: point.raw_output,
        }
    }
}

export default ClientWebappReachableChecker
