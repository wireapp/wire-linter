/**
 * Client-mode checker: Calling (TURN + SFT) reachability.
 * Combines results from TURN UDP/TCP, TURNS (TLS), and SFT checks.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientCallingReachableChecker extends BaseChecker {
    readonly path: string = 'client/calling_reachable'
    readonly name: string = 'Calling reachable (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Checks TURN (1:1 calling) and SFT (conference calling) reachability from this client network. TURN/UDP is preferred for call quality; TCP and TLS are fallbacks.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled.' }
        }

        const issues: string[] = []
        const good: string[] = []

        // Check TURN reachability
        const turn_point = data.get('client/calling/turn_reachable')
        if (turn_point?.value) {
            let turn: Record<string, unknown> | null = null
            try { turn = JSON.parse(String(turn_point.value)) } catch { /* ignore */ }
            if (turn) {
                const any_udp: boolean = turn.any_udp_reachable as boolean ?? false
                const any_tcp: boolean = turn.any_tcp_reachable as boolean ?? false

                if (any_udp) {
                    good.push('TURN reachable via UDP (best quality)')
                } else if (any_tcp) {
                    issues.push('TURN UDP is **blocked** from this network. Calls will use TCP fallback (reduced quality). Configure your firewall to allow UDP on port 3478.')
                } else {
                    // Check TURNS (TLS fallback)
                    const turns_point = data.get('client/calling/turn_tls_reachable')
                    let turns_reachable: boolean = false
                    if (turns_point?.value) {
                        let turns: Record<string, unknown> | null = null
                        try { turns = JSON.parse(String(turns_point.value)) } catch { /* ignore */ }
                        if (turns) turns_reachable = turns.any_reachable as boolean ?? false
                    }

                    if (turns_reachable) {
                        issues.push('TURN is only reachable via TLS on port 5349. Standard UDP and TCP ports are blocked.')
                    } else {
                        issues.push('Cannot reach **any** TURN server from this network (UDP, TCP, TLS all blocked). 1:1 calls will only work if both participants are on the same network (peer-to-peer).')
                    }
                }
            }
        }

        // Check SFT reachability
        if (data.config?.options?.expect_sft) {
            const sft_point = data.get('client/calling/sft_reachable')
            if (sft_point?.value) {
                let sft: Record<string, unknown> | null = null
                try { sft = JSON.parse(String(sft_point.value)) } catch { /* ignore */ }
                if (sft) {
                    if (sft.reachable as boolean) {
                        good.push('SFT signaling endpoint reachable')
                    } else {
                        issues.push('SFT signaling endpoint **not reachable**. Conference calls will not work from this network.')
                    }
                }
            }
        }

        if (issues.length === 0 && good.length > 0) {
            return { status: 'healthy', status_reason: good.join('. ') + '.', display_value: 'reachable', raw_output: turn_point?.raw_output }
        }

        if (issues.length > 0) {
            const has_critical: boolean = issues.some(i => i.includes('Cannot reach'))
            return {
                status: has_critical ? 'unhealthy' : 'warning',
                status_reason: [...good, ...issues].join('\n\n'),
                display_value: has_critical ? 'blocked' : 'degraded',
                raw_output: turn_point?.raw_output,
            }
        }

        return { status: 'gather_failure', status_reason: 'No calling reachability data collected.' }
    }
}

export default ClientCallingReachableChecker
