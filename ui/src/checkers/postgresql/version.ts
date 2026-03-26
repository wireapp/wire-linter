/**
 * Reports the PostgreSQL version.
 *
 * Consumes the databases/postgresql/version target. This is just info,
 * always returns healthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class VersionChecker extends BaseChecker {
    readonly path: string = 'postgresql/version'
    readonly name: string = 'PostgreSQL version'
    readonly category: string = 'Data / PostgreSQL'
    readonly interest = 'Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Reports the running **PostgreSQL version** for operational visibility. Knowing the exact version helps verify compatibility with Wire backend requirements and identify whether security patches are current.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/postgresql/version')

        // No data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL version data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the PostgreSQL nodes\n2. Check that PostgreSQL is running: `pg_isready`\n3. Try querying the version manually: `psql -c "SELECT version()"`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'PostgreSQL version data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL version data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Version target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const version: string = point.value as string

        return {
            status: 'healthy',
            status_reason: 'PostgreSQL is running version **{{pg_version}}**. This is an informational check with no version threshold.',
            display_value: version,
            raw_output: point.raw_output,
            template_data: { pg_version: version },
        }
    }
}

export default VersionChecker
