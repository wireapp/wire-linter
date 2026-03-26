/**
 * Makes sure the Brig ConfigMap (user accounts) lines up with its JSON Schema.
 *
 * Grabs the kubernetes/configmaps/brig target, parses the YAML, and validates
 * all the key sections cassandra, postgresql, elasticsearch, service endpoints,
 * rabbitmq, AWS, email, auth, and TURN config. The schema gets picked automatically
 * based on whatever wire-server version's running.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class BrigConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/brig'
    readonly name: string = 'Brig ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/brig'
    readonly explanation: string = 'Validates the **Brig** (user accounts) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/brig', 'Brig', 'brig')
    }
}

export default BrigConfigmapChecker
