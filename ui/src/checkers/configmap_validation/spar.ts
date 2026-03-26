/**
 * Validates Spar (SSO/SAML/SCIM) ConfigMap against its JSON schema.
 *
 * Grabs the kubernetes/configmaps/spar target, parses the YAML, and validates
 * SAML settings, Cassandra, brig/galley endpoints, and auth timeouts. The schema
 * version picks itself based on whatever wire-server version you've got.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class SparConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/spar'
    readonly name: string = 'Spar ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/spar'
    readonly explanation: string = 'Validates the **Spar** (SSO/SAML/SCIM) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/spar', 'Spar', 'spar')
    }
}

export default SparConfigmapChecker
