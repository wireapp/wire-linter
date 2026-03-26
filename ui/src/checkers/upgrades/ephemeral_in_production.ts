/**
 * Detects if databases-ephemeral or fake-aws charts are running in production.
 *
 * The config/ephemeral_in_production target returns a boolean or string.
 * These test charts don't persist data, so any pod restart causes total
 * data loss. True means ephemeral is deployed (bad), false means we're
 * using production charts (good).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class EphemeralInProductionChecker extends BaseChecker {
    readonly path: string = 'upgrades/ephemeral_in_production'
    readonly name: string = 'databases-ephemeral / fake-aws in production'
    readonly category: string = 'Upgrades / Migrations'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Flags `databases-ephemeral` or `fake-aws` Helm charts running in production. These test/demo charts have **zero data persistence**, so any pod restart causes **total and irreversible data loss**.'

    check(data: DataLookup): CheckResult {
        // Skip when the deployment intentionally uses ephemeral databases
        if (data.config && data.config.options.using_ephemeral_databases) {
            return {
                status: 'not_applicable',
                status_reason: 'Ephemeral databases are intentionally enabled in deployment settings; check skipped.',
                display_value: 'skipped',
                recommendation: 'Ephemeral databases are intentionally enabled in the deployment settings - check skipped.',
            }
        }

        const point = data.get('config/ephemeral_in_production')

        // We couldn't gather the target data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `config/ephemeral_in_production` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can list Helm releases: `helm list -n wire`\n2. Check that the gatherer has permissions to access Helm release metadata\n3. Review the gatherer logs for errors',
                recommendation: 'databases-ephemeral / fake-aws in production data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // If it's a string, check if it's empty
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Ephemeral/test charts detected in production: **{{charts}}**.',
                    fix_hint: '1. List the ephemeral charts currently deployed:\n   ```\n   helm list -n wire | grep -E "ephemeral|fake-aws"\n   ```\n2. **Migrate to production database charts** before removing ephemeral ones:\n   - Deploy persistent Cassandra, Elasticsearch, MinIO, etc.\n   - Migrate data from ephemeral volumes (if any data exists)\n3. Remove the test charts:\n   ```\n   helm uninstall databases-ephemeral -n wire\n   helm uninstall fake-aws -n wire\n   ```\n4. **Warning**: Any data in ephemeral volumes will be lost on pod restart -- migrate first',
                    recommendation: 'databases-ephemeral or fake-aws charts deployed. These are test/demo charts with zero persistence. Any pod restart means total data loss.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { charts: val },
                }
            }

            // Empty string means no ephemeral charts
            return {
                status: 'healthy',
                status_reason: 'No `databases-ephemeral` or `fake-aws` charts are deployed in production.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // True means ephemeral is deployed, which is bad for production
        if (val === true) {
            return {
                status: 'unhealthy',
                status_reason: '`databases-ephemeral` or `fake-aws` charts are deployed in **production**.',
                fix_hint: '1. List the ephemeral charts currently deployed:\n   ```\n   helm list -n wire | grep -E "ephemeral|fake-aws"\n   ```\n2. **Migrate to production database charts** before removing ephemeral ones:\n   - Deploy persistent Cassandra, Elasticsearch, MinIO, etc.\n   - Migrate data from ephemeral volumes (if any data exists)\n3. Remove the test charts:\n   ```\n   helm uninstall databases-ephemeral -n wire\n   helm uninstall fake-aws -n wire\n   ```\n4. **Warning**: Any data in ephemeral volumes will be lost on pod restart -- migrate first',
                recommendation: 'databases-ephemeral or fake-aws charts deployed. These are test/demo charts with zero persistence. Any pod restart means total data loss.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // False means we're using production charts, which is correct
        return {
            status: 'healthy',
            status_reason: 'No `databases-ephemeral` or `fake-aws` charts are deployed in production.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default EphemeralInProductionChecker
