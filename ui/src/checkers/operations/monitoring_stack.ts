/**
 * Checks whether the Prometheus/Grafana monitoring stack is running.
 *
 * Consumes the operations/monitoring_stack target (boolean or string).
 * Without monitoring, issues stay hidden until users complain. Returns
 * warning, not unhealthy, since the deployment keeps working anyway.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class MonitoringStackChecker extends BaseChecker {
    readonly path: string = 'operations/monitoring_stack'
    readonly name: string = 'Prometheus/Grafana monitoring stack running'
    readonly category: string = 'Operations / Tooling'
    readonly interest = 'Health, Setup' as const
    readonly explanation: string = 'Checks whether **Prometheus** and **Grafana** are running. Without a monitoring stack, infrastructure problems go **undetected** until users report them.'

    check(data: DataLookup): CheckResult {
        // Skip when metrics/monitoring is not part of this deployment
        if (data.config && !data.config.options.expect_metrics) {
            return {
                status: 'not_applicable',
                status_reason: 'Metrics monitoring is not enabled in deployment settings; check skipped.',
                display_value: 'skipped',
                recommendation: 'Metrics monitoring is not enabled in the deployment settings - check skipped.',
            }
        }

        const point = data.get('operations/monitoring_stack')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `operations/monitoring_stack` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can access the cluster: `kubectl get pods -n monitoring`\n2. Ensure the monitoring namespace exists and is correct\n3. Review the gatherer logs for permission errors or timeouts',
                recommendation: 'Prometheus/Grafana monitoring stack running data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value non-empty means monitoring is running
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'Prometheus/Grafana monitoring stack is **running**: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            // Missing monitoring is a warning, not unhealthy deployment still works
            return {
                status: 'warning',
                status_reason: 'Prometheus/Grafana monitoring stack is **not running**.',
                fix_hint: '1. Install the `kube-prometheus-stack` Helm chart:\n   ```\n   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts\n   helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace\n   ```\n2. Verify pods are running: `kubectl get pods -n monitoring`\n3. Access Grafana: `kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80`\n4. Import the Wire-specific Grafana dashboards from the Wire documentation',
                recommendation: 'Monitoring stack not running. Nobody knows about problems until users complain.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means monitoring is running
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Prometheus/Grafana monitoring stack is **running**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false monitoring not running (warning, not unhealthy)
        return {
            status: 'warning',
            status_reason: 'Prometheus/Grafana monitoring stack is **not running**.',
            fix_hint: '1. Install the `kube-prometheus-stack` Helm chart:\n   ```\n   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts\n   helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace\n   ```\n2. Verify pods are running: `kubectl get pods -n monitoring`\n3. Access Grafana: `kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80`\n4. Import the Wire-specific Grafana dashboards from the Wire documentation',
            recommendation: 'Monitoring stack not running. Nobody knows about problems until users complain.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default MonitoringStackChecker
