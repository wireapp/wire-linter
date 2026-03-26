/**
 * Checks whether database host configuration is consistent across all services.
 *
 * Consumes the config/database_host_consistency target (boolean or string).
 * If even one service points to the wrong database (or none), you'll get data
 * corruption or the service just stops working.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class DatabaseHostConsistencyChecker extends BaseChecker {
    readonly path: string = 'helm_config/database_host_consistency'
    readonly name: string = 'Database host consistency across all services'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Confirms all Wire services point to the same database hosts (**Cassandra**, **Elasticsearch**, **PostgreSQL**, **MinIO**). A single mismatch causes data corruption or **silent service failures**.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/database_host_consistency')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Database host consistency data was not collected.',
                fix_hint: '1. Verify the gatherer has access to service ConfigMaps:\n   ```\n   kubectl get configmap -n wire\n   ```\n2. Re-run the gatherer ensuring the `config/database_host_consistency` target succeeds.',
                recommendation: 'Couldn\'t collect database host consistency data.',
            }
        }

        // Null value means the gatherer encountered an error collecting this target
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Database host consistency data collection returned null (gatherer error).',
                recommendation: 'Couldn\'t collect database host consistency data.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // Build a recommendation that includes the expected database IPs
        // so the operator knows what the services should be pointing at
        const db = data.config?.databases
        const db_hint: string = db
            ? ` Expected hosts: Cassandra=${db.cassandra}, Elasticsearch=${db.elasticsearch}, PostgreSQL=${db.postgresql}, MinIO=${db.minio}.`
            : ''
        const fail_recommendation: string = `Database host configuration inconsistent across services. One mismatch means a service talks to the wrong (or no) database.${db_hint}`

        // String value: inspect content rather than assuming non-empty means consistent
        if (typeof val === 'string') {
            const lower = val.toLowerCase()

            // Empty string means no data collected or nothing matched
            if (val.length === 0) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Database host configuration is inconsistent across services.',
                    recommendation: fail_recommendation,
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Strings containing negative indicators are unhealthy
            const unhealthy_patterns = ['mismatch', 'inconsistent', 'error', 'fail', 'missing', 'unreachable', 'not found', 'not configured']
            if (unhealthy_patterns.some(pattern => lower.includes(pattern))) {
                return {
                    status: 'unhealthy',
                    status_reason: `Database host configuration issue detected: ${val}.`,
                    recommendation: fail_recommendation,
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Known-good patterns confirm consistency; 'ok' uses exact match to avoid
            // matching 'not ok' as healthy (substring match would be a dangerous false positive)
            const healthy_patterns = ['consistent', 'all match', 'healthy']
            if (healthy_patterns.some(pattern => lower.includes(pattern)) || lower === 'ok') {
                return {
                    status: 'healthy',
                    status_reason: 'All services point to consistent database hosts: `{{hosts}}`.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { hosts: val },
                }
            }

            // Unrecognized string content: report as warning so an operator reviews it
            return {
                status: 'warning',
                status_reason: `Database host consistency returned an unrecognized result: ${val}.`,
                recommendation: `Could not determine consistency from the returned value. Verify manually.${db_hint}`,
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means all hosts are consistent
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All services point to **consistent** database hosts.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false inconsistent database hosts
        return {
            status: 'unhealthy',
            status_reason: 'Database host configuration is **inconsistent** across services.',
            fix_hint: '1. Compare database hosts across all service ConfigMaps:\n   ```\n   kubectl get configmap -n wire brig galley gundeck cargohold spar -o yaml | grep -A2 "cassandra\\|elasticsearch\\|postgresql\\|minio"\n   ```\n2. Ensure all services point to the same hosts in your helm values\n3. Apply the fix:\n   ```\n   helm upgrade wire-server wire/wire-server -f values.yaml\n   ```',
            recommendation: fail_recommendation,
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default DatabaseHostConsistencyChecker
