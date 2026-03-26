/**
 * Checks internet connectivity test results.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class InternetConnectivityChecker extends BaseChecker {
    readonly path: string = 'networking/internet_connectivity'
    readonly name: string = 'Internet connectivity'
    readonly category: string = 'Networking / Calling'
    readonly interest = 'Health' as const
    readonly explanation: string = 'When internet access is declared, verifies actual connectivity via DNS resolution, TCP, and HTTP tests.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.has_internet) {
            return { status: 'not_applicable', status_reason: 'Internet access not declared.' }
        }

        const point = data.get('preflight/internet_connectivity')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Internet connectivity test data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const all_ok: boolean = parsed.all_ok as boolean ?? false
        const details: string = (parsed.details as string) ?? ''

        if (all_ok) {
            return { status: 'healthy', status_reason: `Internet connectivity verified: ${details}`, display_value: 'connected', raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: `Internet access declared but connectivity test **failed**: ${details}. Targets requiring internet (push notifications, AWS endpoints) will fail.`,
            display_value: 'failed',
            raw_output: point.raw_output,
        }
    }
}

export default InternetConnectivityChecker
