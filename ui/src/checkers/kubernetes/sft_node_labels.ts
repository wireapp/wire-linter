/**
 * Makes sure Kubernetes nodes have the SFT scheduling label.
 *
 * We look at the kubernetes/nodes/sft_node_labels target to count how many
 * nodes have wire.link/role=sft. If nodes don't have this label, SFT pods
 * can't be scheduled on the right nodes with proper network access. Check JCT-47.
 *
 * We also check if sftd is actually running. If SFT isn't deployed, the missing
 * label isn't really a problem, just something to note. But if SFT is running,
 * then we need those labels.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, parse_number, type DataLookup } from '../data_lookup'

export class SftNodeLabelsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/sft_node_labels'
    readonly name: string = 'SFT node scheduling labels (see: JCT-47)'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Checks that Kubernetes nodes designated for SFT (conference calling) carry the `wire.link/role=sft` label. Without this label, SFT pods may be scheduled on nodes lacking the required **public IP** and **UDP port access** for WebRTC media.'

    check(data: DataLookup): CheckResult {
        // Skip when calling is not enabled
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled in the deployment configuration.' }
        }

        // Skip when SFT is not part of this deployment
        if (data.config && !data.config.options.expect_sft) {
            return {
                status: 'not_applicable',
                status_reason: 'SFT is not enabled in this deployment — check skipped.',
                display_value: 'skipped',
                recommendation: 'SFT (Selective Forwarding Turn) is not enabled in the deployment settings - check skipped.',
            }
        }

        const point = data.get('kubernetes/nodes/sft_node_labels')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'SFT node label data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/nodes/sft_node_labels\n   ```\n3. Manually check: `kubectl get nodes --show-labels | grep wire.link/role`',
                recommendation: 'SFT node label data not collected.',
            }
        }

        const count = parse_number(point)

        // Unparseable value — treat as collection failure
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'SFT node label count could not be parsed.',
                recommendation: 'SFT node label data was collected but the value could not be parsed as a number.',
                raw_output: point.raw_output,
            }
        }

        // Zero labeled nodes check whether SFT is actually deployed
        if (count === 0) {
            // Cross-reference: if sftd pods exist, the label is needed
            const sftd_point = data.get('wire_services/sftd/healthy')
            const sft_is_deployed: boolean = sftd_point !== undefined && coerce_boolean(sftd_point.value) === true

            if (sft_is_deployed) {
                return {
                    status: 'warning',
                    status_reason: 'SFT is deployed but **no nodes** carry the `wire.link/role=sft` scheduling label.',
                    fix_hint: '1. Add the SFT scheduling label to designated node(s):\n   ```\n   kubectl label node <node-name> wire.link/role=sft\n   ```\n2. Verify the label was applied:\n   ```\n   kubectl get nodes --show-labels | grep wire.link/role\n   ```\n3. SFT nodes need:\n   - A **public IP** address reachable from the internet\n   - **UDP ports** open for WebRTC media traffic\n4. After labeling, SFT pods will be rescheduled to labeled nodes.\n5. See **JCT-47** for details on SFT node requirements.',
                    recommendation: [
                        'SFT is deployed but no Kubernetes nodes have the scheduling label wire.link/role=sft.',
                        'SFT pods may be scheduled on nodes without proper network access (public IP, UDP ports for WebRTC media).',
                        '',
                        'Fix: add the label to designated SFT node(s):',
                        '<command>kubectl label node <node-name> wire.link/role=sft</command>',
                    ].join('\n'),
                    display_value: 0,
                    display_unit: 'nodes',
                    raw_output: point.raw_output,
                }
            }

            // SFT is not deployed label is irrelevant
            return {
                status: 'healthy',
                status_reason: 'SFT is not deployed, so the `wire.link/role=sft` label is not required.',
                recommendation: 'SFT is not deployed - scheduling label not required.',
                display_value: 'n/a (SFT not deployed)',
                raw_output: point.raw_output,
            }
        }

        // At least one node has the SFT label
        return {
            status: 'healthy',
            status_reason: '**{{count}}** node(s) carry the `wire.link/role=sft` scheduling label.',
            display_value: count,
            display_unit: 'nodes',
            raw_output: point.raw_output,
            template_data: { count },
        }
    }
}

export default SftNodeLabelsChecker
