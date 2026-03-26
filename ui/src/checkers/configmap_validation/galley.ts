/**
 * Validates Galley's ConfigMap against JSON Schema covers conversations,
 * teams, settings, feature flags, federation domain, DB connections.
 *
 * Reads the kubernetes/configmaps/galley target, parses the YAML, and checks
 * it matches the schema for your wire-server version (version detection is automatic).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class GalleyConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/galley'
    readonly name: string = 'Galley ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/galley'
    readonly explanation: string = 'Validates the **Galley** (conversations and teams) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/galley', 'Galley', 'galley')
    }
}

export default GalleyConfigmapChecker
