/**
 * Checks the Background Worker ConfigMap against its JSON Schema.
 *
 * Uses the kubernetes/configmaps/background-worker target and validates the
 * config for cassandra clusters, postgresql, rabbitmq, service endpoints,
 * federation domain, and notification pusher stuff. Schema version is picked
 * based on whatever wire-server version is running.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { validate_configmap } from './validate_configmap'

export class BackgroundWorkerConfigmapChecker extends BaseChecker {
    readonly path: string = 'configmap_validation/background_worker'
    readonly name: string = 'Background Worker ConfigMap schema validation'
    readonly category: string = 'ConfigMap Validation'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/configmaps/background-worker'
    readonly explanation: string = 'Validates the **Background Worker** (async tasks) ConfigMap against the JSON Schema for the deployed wire-server version. Invalid configuration can **prevent the service from starting** or cause runtime errors.'

    check(data: DataLookup): CheckResult {
        return validate_configmap(data, 'kubernetes/configmaps/background-worker', 'Background Worker', 'background-worker')
    }
}

export default BackgroundWorkerConfigmapChecker
