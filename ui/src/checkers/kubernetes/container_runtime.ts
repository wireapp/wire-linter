/**
 * Reports what container runtime your Kubernetes nodes are using.
 * This is just informational it always comes back as healthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ContainerRuntimeChecker extends BaseChecker {
    readonly path: string = 'kubernetes/container_runtime'
    readonly name: string = 'Container runtime'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports the **container runtime** (e.g., `containerd`, `CRI-O`) used by Kubernetes nodes. Useful for compatibility checks and troubleshooting container-level issues.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/nodes/container_runtime')

        // Didn't manage to get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Container runtime data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/nodes/container_runtime\n   ```\n3. Manually check: `kubectl get nodes -o wide` (the **CONTAINER-RUNTIME** column).',
                recommendation: 'Couldn\'t get container runtime data.',
            }
        }

        // The collector sets value=null when collection fails
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Container runtime data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Container runtime target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const runtime: string = point.value as string

        return {
            status: 'healthy',
            status_reason: 'Container runtime is **{{runtime}}**.',
            display_value: runtime,
            raw_output: point.raw_output,
            template_data: { runtime },
        }
    }
}

export default ContainerRuntimeChecker
