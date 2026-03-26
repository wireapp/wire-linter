/**
 * Checks whether all Kubernetes nodes are in Ready state.
 *
 * Uses the kubernetes/nodes/all_ready target. If any nodes aren't Ready,
 * they can't take on work, which is a problem.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class AllNodesReadyChecker extends BaseChecker {
    readonly path: string = 'kubernetes/all_nodes_ready'
    readonly name: string = 'All nodes Ready'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies all Kubernetes nodes report **Ready** status. Unready nodes cannot schedule pods, reducing cluster capacity and potentially causing service outages.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/nodes/all_ready')

        // Didn't manage to get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Kubernetes node readiness data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API (`kubectl` configured).\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/nodes/all_ready\n   ```\n3. Manually check node status: `kubectl get nodes`',
                recommendation: 'Couldn\'t get the nodes Ready data.',
            }
        }

        const all_ready = coerce_boolean(point.value)

        // Some nodes aren't Ready can't schedule workloads on them
        if (all_ready === false) {
            return {
                status: 'unhealthy',
                status_reason: 'One or more Kubernetes nodes are **not in Ready state**.',
                fix_hint: '1. Identify which nodes are not Ready:\n   ```\n   kubectl get nodes\n   ```\n2. Check the conditions on the unready node(s):\n   ```\n   kubectl describe node <node-name>\n   ```\n3. Common causes:\n   - **kubelet** not running: `systemctl status kubelet` on the node\n   - **Network plugin** (CNI) misconfigured or crashed\n   - **Disk pressure**, **memory pressure**, or **PID pressure** conditions\n4. Check kubelet logs: `journalctl -u kubelet -f` on the affected node.',
                recommendation: 'Some Kubernetes nodes aren\'t Ready. See what\'s going on with <command>kubectl get nodes</command>.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // All nodes healthy
        if (all_ready === true) {
            return {
                status: 'healthy',
                status_reason: 'All Kubernetes nodes are in Ready state.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `Node readiness data has an unexpected value: ${String(point.value)}`,
            recommendation: 'All nodes Ready returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default AllNodesReadyChecker
