/**
 * Validates the Gundeck ConfigMap (push notifications) against its JSON Schema.
 *
 * Pulls from kubernetes/configmaps/gundeck, parses the YAML, and checks that
 * all required sections are there cassandra, redis, rabbitmq, AWS SQS/SNS,
 * notification settings. Schema version is picked automatically based on the
 * wire-server version it detects.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class GundeckConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/gundeck'
    readonly name: string = 'Gundeck ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/gundeck'
    readonly explanation: string = 'Validates the **Gundeck** (push notifications) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/gundeck', 'Gundeck', 'gundeck')
    }
}

export default GundeckConfigmapChecker
