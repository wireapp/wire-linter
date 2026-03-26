/**
 * Client-mode checker: Wire WebSocket notification endpoint reachability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientWebsocketReachableChecker extends BaseChecker {
    readonly path: string = 'client/websocket_reachable'
    readonly name: string = 'WebSocket reachable (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies that the Wire WebSocket notification endpoint accepts connections from this client network. Wire uses persistent WebSocket connections for real-time notifications.'

    check(data: DataLookup): CheckResult {
        const point = data.get('client/websocket/websocket_reachable')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Client WebSocket reachability data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const reachable: boolean = parsed.reachable as boolean ?? false
        const hostname: string = (parsed.hostname as string) ?? ''
        const upgrade_status: number = (parsed.upgrade_status as number) ?? 0

        if (reachable && upgrade_status === 101) {
            return { status: 'healthy', status_reason: `WebSocket upgrade succeeded at \`wss://${hostname}/\` (HTTP 101).`, display_value: 'upgrade OK', raw_output: point.raw_output }
        }

        if (reachable) {
            return { status: 'healthy', status_reason: `WebSocket endpoint reachable at \`wss://${hostname}/\` (HTTP ${upgrade_status}).`, display_value: `reachable (${upgrade_status})`, raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: `WebSocket upgrade to \`wss://${hostname}/\` **failed** from this network. Wire clients will not receive real-time notifications. Verify that your load balancer supports WebSocket connections and that long-lived connections are not being silently dropped.`,
            display_value: 'not reachable',
            raw_output: point.raw_output,
        }
    }
}

export default ClientWebsocketReachableChecker
