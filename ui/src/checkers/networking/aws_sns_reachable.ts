/**
 * Checks AWS SNS reachability from the Gundeck pod.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class AwsSnsReachableChecker extends BaseChecker {
    readonly path: string = 'networking/aws_sns_reachable'
    readonly name: string = 'AWS SNS reachability'
    readonly category: string = 'Networking / Calling'
    readonly interest = 'Health' as const
    readonly explanation: string = 'When using real AWS for push notifications, gundeck must reach the SNS endpoint. Tested from inside the Gundeck pod.'

    check(data: DataLookup): CheckResult {
        // Skip if using fake-aws
        const push_point = data.get('config/gundeck_push_config')
        if (push_point?.value) {
            let push_data: Record<string, unknown> | null = null
            try { push_data = JSON.parse(String(push_point.value)) } catch { /* ignore */ }
            if (push_data?.is_fake_aws) return { status: 'not_applicable', status_reason: 'Using fake-aws (websocket-only).' }
        }

        const point = data.get('network/aws_sns_reachability')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'AWS SNS reachability test not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        if (parsed.reachable as boolean) {
            return { status: 'healthy', status_reason: `AWS SNS reachable from Gundeck pod: \`${parsed.target_host}\``, raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: `AWS SNS **not reachable** from Gundeck pod (\`${parsed.target_host}\`). Push notifications will fail. Error: ${parsed.error}`,
            raw_output: point.raw_output,
        }
    }
}

export default AwsSnsReachableChecker
