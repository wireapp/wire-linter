/**
 * Checks AWS SQS reachability from the Gundeck pod.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class AwsSqsReachableChecker extends BaseChecker {
    readonly path: string = 'networking/aws_sqs_reachable'
    readonly name: string = 'AWS SQS reachability'
    readonly category: string = 'Networking / Calling'
    readonly interest = 'Health' as const
    readonly explanation: string = 'When using real AWS, gundeck needs access to SQS for device feedback (uninstalled apps, expired push tokens).'

    check(data: DataLookup): CheckResult {
        const push_point = data.get('config/gundeck_push_config')
        if (push_point?.value) {
            let push_data: Record<string, unknown> | null = null
            try { push_data = JSON.parse(String(push_point.value)) } catch { /* ignore */ }
            if (push_data?.is_fake_aws) return { status: 'not_applicable', status_reason: 'Using fake-aws (websocket-only).' }
        }

        const point = data.get('network/aws_sqs_reachability')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'AWS SQS reachability test not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        if (parsed.reachable as boolean) {
            return { status: 'healthy', status_reason: `AWS SQS reachable from Gundeck pod: \`${parsed.target_host}\``, raw_output: point.raw_output }
        }

        return { status: 'unhealthy', status_reason: `AWS SQS **not reachable** from Gundeck pod (\`${parsed.target_host}\`). Error: ${parsed.error}`, raw_output: point.raw_output }
    }
}

export default AwsSqsReachableChecker
