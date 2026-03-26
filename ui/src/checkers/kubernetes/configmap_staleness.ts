/**
 * Detects services running with stale ConfigMap configuration.
 *
 * Compares Deployment pod template annotations (what Helm says new pods
 * should have) against running pod annotations (what pods were actually
 * created with). A mismatch means someone updated the ConfigMap but the
 * service wasn't restarted — pods are still running old config.
 *
 * Consumes two targets per service:
 *   - kubernetes/deployments/template_annotations/<service>
 *   - kubernetes/pods/annotations/<service>
 *
 * Both store JSON strings: the template target has the annotations dict,
 * the pods target has a {pod_name: annotations_dict} map.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

/** Per-service staleness details for unhealthy report */
interface StalenessDetail {
    service: string
    stale_pods: string[]
    mismatched_keys: string[]
}

export class ConfigmapStalenessChecker extends BaseChecker {
    readonly path: string = 'kubernetes/configmap_staleness'
    readonly name: string = 'ConfigMap staleness'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string =
        'Detects services running with **stale ConfigMap configuration**. ' +
        'When a ConfigMap is updated but the service pods are not restarted, ' +
        'pods continue using the old configuration. Helm tracks this via ' +
        '`checksum/` annotations in Deployment pod templates — if running ' +
        'pod checksums differ from the Deployment template, a restart is needed.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const stale_services: StalenessDetail[] = []
        // Services where we confirmed checksums match
        const healthy_services: string[] = []
        // Services we couldn't check (missing data, no checksums, etc.)
        const skipped_services: string[] = []
        let any_data_found: boolean = false
        const raw_outputs: string[] = []

        for (const service of WIRE_CORE_SERVICES) {
            const template_path: string = `kubernetes/deployments/template_annotations/${service}`
            const pods_path: string = `kubernetes/pods/annotations/${service}`

            const template_point = data.get_applicable(template_path)
            const pods_point = data.get_applicable(pods_path)

            // No data collected or service doesn't exist in this deployment
            if (!template_point || !pods_point) {
                skipped_services.push(service)
                continue
            }

            any_data_found = true

            if (template_point.raw_output) raw_outputs.push(template_point.raw_output)
            if (pods_point.raw_output) raw_outputs.push(pods_point.raw_output)

            // Parse the JSON values from target data points
            let template_annotations: Record<string, string>
            let pod_annotations_map: Record<string, Record<string, string>>

            try {
                template_annotations = JSON.parse(String(template_point.value))
                pod_annotations_map = JSON.parse(String(pods_point.value))
            } catch {
                // Malformed JSON — can't compare, skip this service
                skipped_services.push(service)
                continue
            }

            // Find checksum-related annotations in the Deployment template.
            // Helm typically uses checksum/config, checksum/secret, etc.
            const checksum_keys: string[] = Object.keys(template_annotations)
                .filter((key: string) => key.startsWith('checksum/'))

            // No checksum annotations means we can't detect staleness for
            // this service (might be a non-Helm or older Helm deployment)
            if (checksum_keys.length === 0) {
                skipped_services.push(service)
                continue
            }

            // Compare each running pod's checksum annotations against
            // what the Deployment template currently specifies
            const stale_pods: string[] = []
            const mismatched_keys_set: Set<string> = new Set()

            for (const [pod_name, pod_annots] of Object.entries(pod_annotations_map)) {
                for (const key of checksum_keys) {
                    const expected: string = template_annotations[key] ?? ''
                    const actual: string = pod_annots[key] ?? ''

                    // Pod is missing the annotation or has a different value
                    if (actual !== expected) {
                        if (!stale_pods.includes(pod_name)) {
                            stale_pods.push(pod_name)
                        }
                        mismatched_keys_set.add(key)
                    }
                }
            }

            if (stale_pods.length > 0) {
                stale_services.push({
                    service,
                    stale_pods,
                    mismatched_keys: [...mismatched_keys_set],
                })
            } else {
                healthy_services.push(service)
            }
        }

        // No data collected at all
        if (!any_data_found) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment or pod annotation data was collected.',
                fix_hint: '1. Ensure the gatherer has kubectl access\n' +
                    '2. Re-run gathering with Kubernetes targets enabled\n' +
                    '3. Check that deployments exist in the configured namespace',
            }
        }

        // One or more services are stale
        if (stale_services.length > 0) {
            const stale_names: string = stale_services
                .map((s: StalenessDetail) => `**${s.service}**`)
                .join(', ')

            // Build detailed breakdown for the recommendation field
            const details: string = stale_services.map((s: StalenessDetail) => {
                const pod_list: string = s.stale_pods
                    .map((p: string) => `  - \`${p}\``)
                    .join('\n')
                const keys: string = s.mismatched_keys.join(', ')
                return `**${s.service}** (${keys}): ${s.stale_pods.length} stale pod(s)\n${pod_list}`
            }).join('\n\n')

            // Build the fix hint with rollout restart commands
            const restart_commands: string = stale_services
                .map((s: StalenessDetail) => `kubectl rollout restart deployment/${s.service} -n ${ns}`)
                .join('\n')

            return {
                status: 'unhealthy',
                status_reason: '{{stale_count}} service(s) running stale configuration: {{{stale_names}}}.',
                fix_hint: 'Restart the affected services to pick up the new ConfigMap:\n' +
                    '```\n{{{restart_commands}}}\n```\n\n' +
                    'Alternatively, re-run `helm upgrade` which will update checksums ' +
                    'and trigger rolling restarts automatically.',
                recommendation: details,
                display_value: `${stale_services.length} stale`,
                raw_output: raw_outputs.join('\n') || undefined,
                template_data: {
                    stale_count: stale_services.length,
                    stale_names,
                    restart_commands,
                    healthy_count: healthy_services.length,
                    skipped_count: skipped_services.length,
                },
            }
        }

        // All checked services are current
        const status_parts: string[] = [
            `${healthy_services.length} service(s) verified`,
        ]
        if (skipped_services.length > 0) {
            status_parts.push(
                `${skipped_services.length} skipped (no checksum annotations or data)`
            )
        }

        return {
            status: 'healthy',
            status_reason: `All checked services running current configuration. ${status_parts.join(', ')}.`,
            display_value: `${healthy_services.length} current`,
            raw_output: raw_outputs.join('\n') || undefined,
            template_data: {
                stale_count: 0,
                stale_names: '',
                restart_commands: '',
                healthy_count: healthy_services.length,
                skipped_count: skipped_services.length,
            },
        }
    }
}

export default ConfigmapStalenessChecker
