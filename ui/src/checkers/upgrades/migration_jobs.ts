/**
 * Verifies that all migration jobs have finished.
 *
 * The migrations/jobs_completed target returns a boolean or string.
 * We're watching for completion of cassandra-migrations, elasticsearch-index-create,
 * brig-index-migrate-data, galley-migrate-data, and spar-migrate-data.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class MigrationJobsChecker extends BaseChecker {
    readonly path: string = 'upgrades/migration_jobs'
    readonly name: string = 'Schema/data migration jobs completed'
    readonly category: string = 'Upgrades / Migrations'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Tracks completion of schema and data migration jobs (`cassandra-migrations`, `elasticsearch-index-create`, `brig/galley/spar-migrate-data`). Incomplete migrations leave the database in an **inconsistent state** and can cause runtime errors.'

    check(data: DataLookup): CheckResult {
        const point = data.get('migrations/jobs_completed')

        // We couldn't gather the target data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `migrations/jobs_completed` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer can list jobs: `kubectl get jobs -n wire`\n2. Check that the Wire namespace is correct\n3. Review the gatherer logs for permission errors or timeouts',
                recommendation: 'Schema/data migration jobs completed data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // If it's a string, non-empty means migrations are done
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'All schema/data migration jobs have **completed**: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'One or more schema/data migration jobs have **not completed**.',
                fix_hint: '1. Check the status of all migration jobs:\n   ```\n   kubectl get jobs -n wire | grep -E "cassandra-migrations|elasticsearch-index|migrate-data"\n   ```\n2. Inspect failed job logs:\n   ```\n   kubectl logs -n wire job/<job-name> --tail=100\n   ```\n3. For stuck jobs, check if the pod is in `CrashLoopBackOff`: `kubectl get pods -n wire | grep migrate`\n4. Common fixes:\n   - **cassandra-migrations**: ensure Cassandra is healthy first\n   - **elasticsearch-index-create**: verify ES cluster is green\n   - **brig/galley/spar-migrate-data**: check database connectivity\n5. Re-run a failed job: `kubectl delete job <job-name> -n wire` then redeploy',
                recommendation: 'Schema/data migration jobs not all completed. Check cassandra-migrations, elasticsearch-index-create, brig-index-migrate-data, galley-migrate-data, spar-migrate-data.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // True means all jobs are done
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All schema/data migration jobs have **completed successfully**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // False means some jobs haven't finished
        return {
            status: 'unhealthy',
            status_reason: 'One or more schema/data migration jobs have **not completed**.',
            fix_hint: '1. Check the status of all migration jobs:\n   ```\n   kubectl get jobs -n wire | grep -E "cassandra-migrations|elasticsearch-index|migrate-data"\n   ```\n2. Inspect failed job logs:\n   ```\n   kubectl logs -n wire job/<job-name> --tail=100\n   ```\n3. For stuck jobs, check if the pod is in `CrashLoopBackOff`: `kubectl get pods -n wire | grep migrate`\n4. Common fixes:\n   - **cassandra-migrations**: ensure Cassandra is healthy first\n   - **elasticsearch-index-create**: verify ES cluster is green\n   - **brig/galley/spar-migrate-data**: check database connectivity\n5. Re-run a failed job: `kubectl delete job <job-name> -n wire` then redeploy',
            recommendation: 'Schema/data migration jobs not all completed. Check cassandra-migrations, elasticsearch-index-create, brig-index-migrate-data, galley-migrate-data, spar-migrate-data.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default MigrationJobsChecker
