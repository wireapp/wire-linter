/**
 * Validates the Cannon ConfigMap against its JSON Schema.
 *
 * Pulls in the kubernetes/configmaps/cannon target, parses the YAML,
 * and checks for required sections: gundeck endpoint, cassandra, rabbitmq,
 * and drain options. The schema version picks itself based on what
 * wire-server version it finds. (WebSocket push, btw.)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class CannonConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/cannon'
    readonly name: string = 'Cannon ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/cannon'
    readonly explanation: string = 'Validates the **Cannon** (WebSocket) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/cannon', 'Cannon', 'cannon')
    }
}

export default CannonConfigmapChecker
