/**
 * Checks container image consistency across kubenodes (Wire-managed only).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class NodeImageConsistencyChecker extends BaseChecker {
    readonly path: string = 'kubernetes/node_image_consistency'
    readonly name: string = 'Node image consistency'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly requires_ssh: boolean = true
    readonly explanation: string = 'In Wire-managed offline clusters, images are pre-loaded on each node. This check finds images present on some nodes but missing on others — a rescheduled pod would fail.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.wire_managed_cluster) {
            return { status: 'not_applicable', status_reason: 'Not a Wire-managed cluster.' }
        }

        const point = data.get('kubernetes/node_image_inventory')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Node image inventory not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const count: number = (parsed.inconsistent_count as number) ?? 0
        if (count === 0) {
            return { status: 'healthy', status_reason: `All container images consistent across kubenodes (${parsed.total_unique_images} unique images).`, display_value: 'consistent', raw_output: point.raw_output }
        }

        const items: Array<Record<string, unknown>> = (parsed.inconsistent_images as Array<Record<string, unknown>>) ?? []
        const sample: string = items.slice(0, 3).map(i => `\`${i.image}\``).join(', ')

        return {
            status: 'warning',
            status_reason: `**${count}** image(s) are missing on some nodes: ${sample}${count > 3 ? ` and ${count - 3} more` : ''}. If a pod is rescheduled to a node missing its image, it will fail.`,
            fix_hint: 'Pre-load missing images onto affected nodes:\n```\ncrictl pull <image> || ctr -n k8s.io images import <image.tar>\n```',
            display_value: `${count} inconsistent`,
            raw_output: point.raw_output,
        }
    }
}

export default NodeImageConsistencyChecker
