/**
 * Checks that Wire services aren't running with Debug log level in production.
 *
 * Consumes configmap data for all Wire core services (brig, galley, gundeck,
 * cannon, cargohold, spar, background-worker). Debug logging in production
 * is a problem, creates way too much log volume, crushes performance, and can
 * leak sensitive data.
 */

// External
import yaml from 'js-yaml'

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

/**
 * Recursively walks an object tree and collects all values found under keys
 * named 'logLevel' (case-sensitive match — Wire Haskell configs use this exact
 * casing). Returns them lowercased for easy comparison.
 */
function _find_log_levels(obj: unknown): string[] {
    const results: string[] = []

    if (!obj || typeof obj !== 'object') return results

    // Arrays: recurse into each element
    if (Array.isArray(obj)) {
        for (const item of obj) {
            results.push(..._find_log_levels(item))
        }
        return results
    }

    // Object: check keys, recurse into values
    for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
        if (key === 'logLevel' && typeof value === 'string') {
            results.push(value.toLowerCase())
        }
        // Always recurse deeper regardless of whether this key matched
        results.push(..._find_log_levels(value))
    }

    return results
}

// Services to check and their configmap target paths
const _SERVICES: Array<{ name: string; target_path: string }> = [
    { name: 'brig',              target_path: 'kubernetes/configmaps/brig' },
    { name: 'galley',            target_path: 'kubernetes/configmaps/galley' },
    { name: 'gundeck',           target_path: 'kubernetes/configmaps/gundeck' },
    { name: 'cannon',            target_path: 'kubernetes/configmaps/cannon' },
    { name: 'cargohold',         target_path: 'kubernetes/configmaps/cargohold' },
    { name: 'spar',              target_path: 'kubernetes/configmaps/spar' },
    { name: 'background-worker', target_path: 'kubernetes/configmaps/background-worker' },
]

export class ServiceLogLevelsChecker extends BaseChecker {
    readonly path: string = 'helm_config/service_log_levels'
    readonly name: string = 'No services running at Debug log level'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Flags any Wire service running at **Debug** log level in production. Debug logging generates excessive volume, **degrades performance**, and can leak sensitive data into log storage.'

    check(data: DataLookup): CheckResult {
        const debug_services: string[] = []
        let checked_count: number = 0

        for (const service of _SERVICES) {
            const point = data.get(service.target_path)
            if (!point || typeof point.value !== 'string' || point.value.length === 0) continue

            const raw_yaml: string = String(point.value)
            let parsed: Record<string, unknown>

            try {
                parsed = yaml.load(raw_yaml) as Record<string, unknown>
            } catch {
                // YAML parse error, skip it the configmap validator will catch it
                continue
            }

            if (!parsed || typeof parsed !== 'object') continue
            checked_count++

            // Walk the entire config tree — logLevel can be nested at any depth
            const found_levels: string[] = _find_log_levels(parsed)

            if (found_levels.some(level => level === 'debug')) {
                debug_services.push(service.name)
            }
        }

        // Didn't get any configmap data
        if (checked_count === 0) {
            return {
                status: 'warning',
                status_reason: 'No service ConfigMap data was available to check log levels.',
                fix_hint: '1. Verify service ConfigMaps exist:\n   ```\n   kubectl get configmap -n wire brig galley gundeck cannon cargohold spar background-worker\n   ```\n2. Re-run the gatherer ensuring the `kubernetes/configmaps/*` targets succeed.',
                recommendation: 'No service configmap data to check log levels.',
            }
        }

        if (debug_services.length > 0) {
            const service_list = debug_services.join(', ')
            return {
                status: 'warning',
                status_reason: '**{{service_count}}** service(s) running at **Debug** log level: `{{service_list}}`.',
                fix_hint: '1. Check the current log levels:\n   ```\n   kubectl get configmap -n wire {{service_list}} -o yaml | grep logLevel\n   ```\n2. Change `logLevel` from `Debug` to `Info` or `Warn` in your helm values for the affected services\n3. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
                recommendation: `${debug_services.length} service(s) set to Debug log level: ${service_list}. That's bad in prod, creates way too much logging, kills performance, and can leak sensitive stuff. Use Info or Warn.`,
                display_value: `Debug: ${service_list}`,
                template_data: { service_count: debug_services.length, service_list },
            }
        }

        return {
            status: 'healthy',
            status_reason: '**{{checked_count}}** service(s) checked, none running at Debug log level.',
            display_value: `${checked_count} services checked`,
            template_data: { checked_count },
        }
    }
}

export default ServiceLogLevelsChecker
