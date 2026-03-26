/**
 * Checks if Cargohold's ConfigMap actually matches the JSON Schema.
 *
 * Pulls the kubernetes/configmaps/cargohold target, parses the YAML, and validates
 * that S3/MinIO config, brig endpoint, and federation settings are all correct.
 * Picks the right schema version based on what wire-server version you're running.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class CargoholdConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/cargohold'
    readonly name: string = 'Cargohold ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/cargohold'
    readonly explanation: string = 'Validates the **Cargohold** (file storage) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/cargohold', 'Cargohold', 'cargohold')
    }
}

export default CargoholdConfigmapChecker
