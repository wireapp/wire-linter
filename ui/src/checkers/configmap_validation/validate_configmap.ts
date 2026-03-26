/**
 * Shared helper for ConfigMap schema validation checkers.
 *
 * Figures out which wire-server version is deployed, grabs the right JSON Schema
 * from the registry, parses the YAML ConfigMap, and validates it with ajv.
 * Spits back a CheckResult with version context and individual validation errors
 * in the recommendation field.
 *
 * validate_configmap handles version detection, schema lookup, YAML parsing,
 * and AJV validation for any ConfigMap checker.
 */

// External
import Ajv from 'ajv'
import yaml from 'js-yaml'

// Ours
import type { CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { detect_wire_server_version, get_versioned_schema } from './schema_registry'

// Single ajv instance used by all configmap checkers
const ajv = new Ajv({ allErrors: true, strict: false })

// Cache compiled validators so we don't recompile schemas on every checker run
const validator_cache = new Map<string, ReturnType<typeof ajv.compile>>()

/**
 * Validate a ConfigMap's YAML against the right JSON Schema for that wire-server version.
 *
 * Figures out what version is deployed from helm data, grabs the matching schema,
 * validates the YAML. Always includes the version in the result so operators know
 * what schema was used.
 *
 * @param data DataLookup instance with the target and helm version data
 * @param target_path ConfigMap target path (e.g., «kubernetes/configmaps/brig»)
 * @param service_name Service name for error messages (e.g., «Brig»)
 * @param service_key Schema registry key (e.g., «brig», «background-worker»)
 * @returns CheckResult with validation status, version, and any errors
 */
export function validate_configmap(
    data: DataLookup,
    target_path: string,
    service_name: string,
    service_key: string,
): CheckResult {
    // Get the wire-server version that's deployed
    const detected_version = detect_wire_server_version(data)

    // Can't pick a schema without knowing the version
    if (!detected_version) {
        return {
            status: 'warning',
            status_reason: 'Could not detect **wire-server version** for schema selection.',
            fix_hint: '1. Check that helm data was collected:\n   ```\n   helm list -n wire\n   ```\n2. Ensure the `helm/release_status` or `wire_services/brig/healthy` target succeeded during gathering\n3. Re-run the gatherer with proper Kubernetes and Helm access.',
            recommendation: `${service_name} ConfigMap validation needs wire-server version detection. ` +
                'Make sure helm/release_status or wire_services/brig/healthy data is collected.',
            template_data: { service_name },
        }
    }

    // Get the schema for this version (uses the highest known version that's <= detected)
    const schema_result = get_versioned_schema(detected_version, service_key)

    // No schema for this version probably a newer release that ditched configmaps
    if (!schema_result) {
        return {
            status: 'warning',
            status_reason: 'No schema available for wire-server **{{detected_version}}** (configmaps removed in 5.28+).',
            fix_hint: 'ConfigMap validation is not available for wire-server versions **5.28+** where configmaps were removed. No action needed if you are on a version that uses Kubernetes secrets or environment-based configuration instead.',
            recommendation: `ConfigMap validation not available for wire-server ${detected_version} ` +
                '(configmaps removed in 5.28+).',
            template_data: { service_name, detected_version },
        }
    }

    const { schema, schema_version } = schema_result

    const point = data.get(target_path)

    // No ConfigMap data collected
    if (!point) {
        return {
            status: 'gather_failure',
            status_reason: '**{{service_name}}** ConfigMap data was not collected.',
            fix_hint: '1. Verify the ConfigMap exists:\n   ```\n   kubectl get configmap {{service_key}} -n wire -o yaml\n   ```\n2. Re-run the gatherer ensuring the `{{target_path}}` target succeeds.',
            recommendation: `${service_name} ConfigMap data not collected.`,
            template_data: { service_name, service_key, target_path },
        }
    }

    const raw_yaml = String(point.value)

    // Value is blank or missing
    if (!raw_yaml.trim()) {
        return {
            status: 'unhealthy',
            status_reason: '**{{service_name}}** ConfigMap is **empty**.',
            fix_hint: '1. View the current ConfigMap:\n   ```\n   kubectl get configmap {{service_key}} -n wire -o yaml\n   ```\n2. Redeploy with correct helm values to populate the ConfigMap:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: `${service_name} ConfigMap is empty.`,
            raw_output: point.raw_output,
            template_data: { service_name, service_key },
        }
    }

    // Parse the YAML
    let parsed: unknown
    try {
        parsed = yaml.load(raw_yaml)
    } catch (parse_error: unknown) {
        const message = parse_error instanceof Error ? parse_error.message : String(parse_error)
        return {
            status: 'unhealthy',
            status_reason: '**{{service_name}}** ConfigMap contains **invalid YAML**.',
            fix_hint: '1. View the current ConfigMap:\n   ```\n   kubectl get configmap {{service_key}} -n wire -o yaml\n   ```\n2. Fix the YAML syntax error: `{{parse_message}}`\n3. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: `${service_name} ConfigMap has invalid YAML: ${message}`,
            raw_output: point.raw_output,
            template_data: { service_name, service_key, parse_message: message },
        }
    }

    // YAML parsed to nothing (empty document)
    if (parsed === null || parsed === undefined) {
        return {
            status: 'unhealthy',
            status_reason: '**{{service_name}}** ConfigMap parsed to an **empty document**.',
            fix_hint: '1. View the current ConfigMap:\n   ```\n   kubectl get configmap {{service_key}} -n wire -o yaml\n   ```\n2. The ConfigMap data key exists but contains no valid YAML content\n3. Redeploy with correct helm values:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: `${service_name} ConfigMap parsed to empty document.`,
            raw_output: point.raw_output,
            configmap_data: raw_yaml,
            template_data: { service_name, service_key },
        }
    }

    // Run it through the schema, using cached validator if available
    const cache_key = `${schema_version}/${service_key}`
    let validate = validator_cache.get(cache_key)
    if (!validate) {
        validate = ajv.compile(schema)
        validator_cache.set(cache_key, validate)
    }
    const is_valid = validate(parsed)

    if (!is_valid && validate.errors) {
        // Format errors so they're readable
        const error_lines: string[] = validate.errors.map((error) => {
            const path = error.instancePath || '(root)'
            const message = error.message || 'unknown error'

            // For missing required properties, call out which one is missing
            if (error.keyword === 'required' && error.params && 'missingProperty' in error.params) {
                return `${path}: missing required property '${error.params.missingProperty}'`
            }

            return `${path}: ${message}`
        })

        // Remove duplicate errors
        const unique_errors = [...new Set(error_lines)]

        return {
            status: 'unhealthy',
            status_reason: '**{{service_name}}** ConfigMap has **{{error_count}}** validation error(s) against schema **{{schema_version}}**.',
            fix_hint: '1. View the current ConfigMap:\n   ```\n   kubectl get configmap {{service_key}} -n wire -o yaml\n   ```\n2. Compare against the schema for version **{{schema_version}}**\n3. Fix the listed validation errors in your helm values\n4. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: `Wire-server version ${detected_version} detected, ` +
                `validated against schema ${schema_version}.\n\n` +
                `${unique_errors.length} validation error(s):\n${unique_errors.join('\n')}`,
            display_value: `${unique_errors.length} error(s)`,
            raw_output: point.raw_output,
            configmap_data: raw_yaml,
            template_data: { service_name, service_key, detected_version, schema_version, error_count: unique_errors.length },
        }
    }

    return {
        status: 'healthy',
        status_reason: '**{{service_name}}** ConfigMap validated successfully against schema **{{schema_version}}**.',
        display_value: `valid (schema: ${schema_version})`,
        raw_output: point.raw_output,
        configmap_data: raw_yaml,
        template_data: { service_name, schema_version },
    }
}
