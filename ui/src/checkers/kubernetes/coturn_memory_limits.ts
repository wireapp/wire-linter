/**
 * Checks whether coturn pods have memory limits set.
 * Without them, coturn can hit the OOM killer under heavy call load and drop
 * all active TURN relay sessions (see WPB-17666).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class CoturnMemoryLimitsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/coturn_memory_limits'
    readonly name: string = 'Coturn pods have memory limits (see: WPB-17666)'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies coturn pods have **memory limits** configured. Without limits, coturn can consume unbounded memory under heavy call load, triggering the OOM killer and dropping all active TURN relay sessions.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pods/coturn_memory_limits')

        // Didn't manage to get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Coturn memory limits data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/pods/coturn_memory_limits\n   ```\n3. Manually check coturn pod resource limits:\n   ```\n   kubectl get pods -l app=coturn -o jsonpath=\'{range .items[*]}{.spec.containers[*].resources}{\"\\n\"}{end}\'\n   ```',
                recommendation: 'Couldn\'t get coturn memory limits data.',
            }
        }

        const val = point.value as boolean | string | number

        // Boolean true all coturn containers have memory limits
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All coturn containers have **memory limits** configured.',
                display_value: 'limits set',
                raw_output: point.raw_output,
            }
        }

        // Boolean false one or more coturn containers don't have memory limits
        if (val === false) {
            return {
                status: 'unhealthy',
                status_reason: 'One or more coturn containers are **missing memory limits**.',
                fix_hint: '1. Add `resources.limits.memory` to your coturn Helm values:\n   ```yaml\n   resources:\n     limits:\n       memory: "512Mi"\n     requests:\n       memory: "256Mi"\n   ```\n2. Apply the change:\n   ```\n   helm upgrade coturn <chart> -f values.yaml -n <namespace>\n   ```\n3. Verify the limits are set on the new pods:\n   ```\n   kubectl get pods -l app=coturn -o jsonpath=\'{range .items[*]}{.spec.containers[*].resources}{\"\\n\"}{end}\'\n   ```\n4. See **WPB-17666** for details on the OOM issue under heavy call load.',
                recommendation: 'One or more coturn containers don\'t have memory limits. When you hit heavy call load, coturn will trigger the OOM killer and drop all active TURN sessions. Add resources.limits.memory to your coturn Helm values.',
                display_value: 'limits missing',
                raw_output: point.raw_output,
            }
        }

        // String value, can't really evaluate it
        return {
            status: 'warning',
            status_reason: 'Unexpected non-boolean value returned for coturn memory limits: "{{val}}".',
            fix_hint: '1. The check returned an unexpected value instead of a boolean.\n2. Manually verify coturn pod memory limits:\n   ```\n   kubectl get pods -l app=coturn -o jsonpath=\'{range .items[*]}{.spec.containers[*].resources}{\"\\n\"}{end}\'\n   ```\n3. Ensure `resources.limits.memory` is set in coturn Helm values.',
            recommendation: 'Can\'t tell if coturn has memory limits or not.',
            display_value: String(val),
            raw_output: point.raw_output,
            template_data: { val },
        }
    }
}

export default CoturnMemoryLimitsChecker
