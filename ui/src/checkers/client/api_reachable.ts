/**
 * Client-mode checker: Wire API (nginz) reachability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientApiReachableChecker extends BaseChecker {
    readonly path: string = 'client/api_reachable'
    readonly name: string = 'API reachable (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies that the Wire API (nginz-https) is reachable from this client network. This is the main REST API for all Wire operations.'

    check(data: DataLookup): CheckResult {
        const point = data.get('client/http/api_reachable')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Client API reachability data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const reachable: boolean = parsed.reachable as boolean ?? false
        const url: string = (parsed.url as string) ?? ''
        const status_code: number = (parsed.status_code as number) ?? 0

        if (reachable) {
            return { status: 'healthy', status_reason: `API reachable: \`${url}\` (HTTP ${status_code}).`, display_value: `reachable`, raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: `Cannot reach the Wire API at \`${url}\` from this network. No Wire client can function without API access.`,
            display_value: 'not reachable',
            raw_output: point.raw_output,
        }
    }
}

export default ClientApiReachableChecker
