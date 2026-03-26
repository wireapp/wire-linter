/**
 * Checks for pods stuck in ImagePullBackOff or ErrImagePull.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ImagePullIssuesChecker extends BaseChecker {
    readonly path: string = 'kubernetes/image_pull_issues'
    readonly name: string = 'Container image pull issues'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Detects pods stuck in `ImagePullBackOff` or `ErrImagePull`. In offline deployments without an image registry, this happens when containerd evicts images from local storage.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/image_pull_issues')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Image pull issues data not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const total: number = (parsed.total_affected as number) ?? 0
        if (total === 0) {
            return { status: 'healthy', status_reason: 'No pods have image pull issues.', display_value: '0 affected', raw_output: point.raw_output }
        }

        const pods: Array<Record<string, string>> = (parsed.affected_pods as Array<Record<string, string>>) ?? []
        const pod_list: string = pods.slice(0, 5).map(p => `\`${p.pod}\` (image: \`${p.image}\`)`).join(', ')

        return {
            status: 'unhealthy',
            status_reason: `**${total}** pod(s) stuck with image pull failures: ${pod_list}${total > 5 ? ` and ${total - 5} more` : ''}.`,
            fix_hint: 'Re-load missing images onto the affected nodes:\n```\ncrictl pull <image> || ctr -n k8s.io images import <image.tar>\n```',
            display_value: `${total} affected`,
            raw_output: point.raw_output,
        }
    }
}

export default ImagePullIssuesChecker
