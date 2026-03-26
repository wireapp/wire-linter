/**
 * Checks how many Kubernetes nodes you've got running.
 *
 * Pulls from kubernetes/nodes/count. We need at least 3 nodes to keep
 * things running smoothly with high availability. Anything less and we flag it.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class NodeCountChecker extends BaseChecker {
    readonly path: string = 'kubernetes/node_count'
    readonly name: string = 'Node count'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health, Setup' as const
    readonly explanation: string = 'Confirms the cluster has at least **3 Kubernetes nodes** for high availability. Fewer nodes mean a single node failure can take down the entire Wire deployment.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/nodes/count')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Kubernetes node count data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/nodes/count\n   ```\n3. Manually check: `kubectl get nodes`',
                recommendation: 'Node count data not collected.',
            }
        }

        const count = parse_number(point)

        // Value couldn't be parsed as a number (gatherer may emit a string or null)
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Kubernetes node count value could not be parsed as a number.',
                recommendation: 'The gathered node count data was not in a recognized numeric format.',
                raw_output: point.raw_output,
            }
        }

        // Fewer than 3 nodes cannot sustain high availability
        if (count < 3) {
            return {
                status: 'unhealthy',
                status_reason: 'Only **{{count}}** Kubernetes node(s) found, which is below the minimum of **3** for high availability.',
                fix_hint: '1. Wire requires a minimum of **3** Kubernetes nodes for high availability.\n2. Add additional nodes to the cluster:\n   ```\n   kubeadm join <control-plane-endpoint> --token <token> --discovery-token-ca-cert-hash sha256:<hash>\n   ```\n3. If the join token has expired, create a new one on the control-plane:\n   ```\n   kubeadm token create --print-join-command\n   ```\n4. Verify the new nodes are Ready: `kubectl get nodes`\n5. With fewer than 3 nodes, a single node failure takes down the entire deployment.',
                recommendation: 'Wire requires minimum 3 Kubernetes nodes for high availability.',
                display_value: count,
                raw_output: point.raw_output,
                template_data: { count },
            }
        }

        return {
            status: 'healthy',
            status_reason: '**{{count}}** Kubernetes node(s) found, meeting the minimum of **3** for high availability.',
            display_value: count,
            raw_output: point.raw_output,
            template_data: { count },
        }
    }
}

export default NodeCountChecker
