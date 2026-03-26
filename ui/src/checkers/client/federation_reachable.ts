/**
 * Client-mode checker: federator endpoint reachability.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClientFederationReachableChecker extends BaseChecker {
    readonly path: string = 'client/federation_reachable'
    readonly name: string = 'Federator reachable (client)'
    readonly category: string = 'Client Reachability'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Checks if the federator endpoint is reachable from this client network. Clients don\'t directly contact the federator, but reachability indicates it is publicly accessible.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_federation) {
            return { status: 'not_applicable', status_reason: 'Federation is not enabled.' }
        }

        const point = data.get('client/federation/federator_reachable')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Federator reachability data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const reachable: boolean = parsed.reachable as boolean ?? false
        const hostname: string = (parsed.hostname as string) ?? ''
        const tls: boolean = parsed.tls_offered as boolean ?? false

        if (reachable) {
            return { status: 'healthy', status_reason: `Federator reachable at \`${hostname}:443\`${tls ? ' (TLS offered)' : ''}.`, display_value: 'reachable', raw_output: point.raw_output }
        }

        // Federator not reachable is informational, not a failure —
        // clients don't directly connect to the federator
        return {
            status: 'healthy',
            status_reason: `Federator at \`${hostname}:443\` is not reachable from this network. This is informational — clients do not directly contact the federator. Federation communication is backend-to-backend.`,
            display_value: 'not reachable (informational)',
            raw_output: point.raw_output,
        }
    }
}

export default ClientFederationReachableChecker
