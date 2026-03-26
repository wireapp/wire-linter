/**
 * Checks if the Kubernetes Metrics API is available.
 *
 * This uses the kubernetes/metrics_api target. If it's missing, kubectl top
 * and HPA autoscaling won't work. We flag this as a warning instead of
 * unhealthy because things keep running without it.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class MetricsApiChecker extends BaseChecker {
    readonly path: string = 'kubernetes/metrics_api'
    readonly name: string = 'Metrics API available'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health, Setup' as const
    readonly explanation: string = 'Checks whether the **Kubernetes Metrics API** (`metrics-server`) is available. Without it, `kubectl top` and `HorizontalPodAutoscaler` cannot function, preventing resource monitoring and automatic scaling.'

    check(data: DataLookup): CheckResult {
        // Skip when metrics/monitoring is not part of this deployment
        if (data.config && !data.config.options.expect_metrics) {
            return {
                status: 'not_applicable',
                status_reason: 'Metrics monitoring is not enabled in the deployment settings, so this check was skipped.',
                display_value: 'skipped',
                recommendation: 'Metrics monitoring is not enabled in the deployment settings - check skipped.',
            }
        }

        const point = data.get('kubernetes/metrics_api')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Metrics API availability data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/metrics_api\n   ```\n3. Manually check: `kubectl top nodes` (will fail if Metrics API is unavailable).',
                recommendation: 'Metrics API available data not collected.',
            }
        }

        const is_available = coerce_boolean(point.value)

        // Value couldn't be interpreted as a boolean at all
        if (typeof is_available !== 'boolean') {
            return {
                status: 'gather_failure',
                status_reason: `Metrics API availability returned an unexpected value: ${JSON.stringify(point.value)}.`,
                recommendation: 'Metrics API data could not be interpreted. Re-run the gatherer.',
                raw_output: point.raw_output,
            }
        }

        // If Metrics API is missing, monitoring and autoscaling won't work
        if (is_available === false) {
            return {
                status: 'warning',
                status_reason: 'Kubernetes **Metrics API** is not available in this cluster.',
                fix_hint: '1. Install `metrics-server`:\n   ```\n   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml\n   ```\n2. Or install a full monitoring stack like `kube-prometheus-stack` via Helm:\n   ```\n   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts\n   helm install kube-prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace\n   ```\n3. Verify the Metrics API is working:\n   ```\n   kubectl top nodes\n   kubectl top pods -A\n   ```\n4. Without the Metrics API, `kubectl top` and `HorizontalPodAutoscaler` will not function.',
                recommendation: 'Metrics API not available. Install metrics-server or kube-prometheus-stack for resource monitoring via <command>kubectl top</command>.',
                display_value: is_available,
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Kubernetes **Metrics API** is available.',
            display_value: is_available,
            raw_output: point.raw_output,
        }
    }
}

export default MetricsApiChecker
