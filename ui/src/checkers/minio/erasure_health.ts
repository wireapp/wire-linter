/**
 * Checks if MinIO can actually write or if it's stuck in read-only.
 *
 * Uses databases/minio/erasure_health, which tells us:
 * boolean true = read-write (all good)
 * boolean false = read-only (lost quorum)
 * string «read-write» or «read-only»
 *
 * When you lose quorum, the whole thing locks down to read-only. Nobody
 * can upload anything, which pretty much breaks the whole app.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ErasureHealthChecker extends BaseChecker {
    readonly path: string = 'minio/erasure_health'
    readonly name: string = 'Erasure set health / quorum mode'
    readonly category: string = 'Data / MinIO'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Monitors whether MinIO has **write quorum** across its erasure sets. When quorum is lost, MinIO drops to **read-only mode** and all file uploads in Wire fail.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/minio/erasure_health')

        // Couldn't get the quorum data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO erasure/quorum health data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the MinIO host\n2. Check that `mc admin info <alias>` returns erasure set information\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'No erasure/quorum data available.',
            }
        }

        // Gatherer command failed and returned null
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO erasure/quorum health data could not be retrieved.',
                recommendation: 'No erasure/quorum data available.',
                raw_output: point.raw_output,
            }
        }

        const val: boolean | string | number = point.value as boolean | string | number

        // Boolean response: true means we're good, false means trouble
        if (typeof val === 'boolean') {
            if (val) {
                return {
                    status: 'healthy',
                    status_reason: 'MinIO erasure sets have quorum and are operating in **read-write** mode.',
                    display_value: 'read-write',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'MinIO has **lost quorum** and dropped to **read-only** mode — all uploads will fail.',
                fix_hint: '1. Check cluster status: `mc admin info <alias>`\n2. Identify which nodes or drives are down\n3. Bring failed nodes back online or replace failed drives\n4. Run a heal operation: `mc admin heal -r <alias>`\n5. Verify quorum is restored: `mc admin info <alias>` should show **read-write**',
                recommendation: 'MinIO lost quorum and went read-only. Nothing can be uploaded.',
                display_value: 'read-only',
                raw_output: point.raw_output,
            }
        }

        // Numeric response: nonzero means healthy, zero means unhealthy
        if (typeof val === 'number') {
            if (val > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'MinIO erasure sets have quorum and are operating in read-write mode.',
                    display_value: 'read-write',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'MinIO has lost quorum and dropped to read-only mode — all uploads will fail.',
                recommendation: 'MinIO lost quorum and went read-only. Nothing can be uploaded.',
                display_value: 'read-only',
                raw_output: point.raw_output,
            }
        }

        // String response see if it says read-only
        if (val.toLowerCase().includes('read-only')) {
            return {
                status: 'unhealthy',
                status_reason: 'MinIO reports **{{erasure_value}}** — quorum is lost and uploads will fail.',
                fix_hint: '1. Check cluster status: `mc admin info <alias>`\n2. Identify which nodes or drives are down\n3. Bring failed nodes back online or replace failed drives\n4. Run a heal operation: `mc admin heal -r <alias>`\n5. Verify quorum is restored: `mc admin info <alias>` should show **read-write**',
                recommendation: 'MinIO lost quorum and went read-only. Nothing can be uploaded.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { erasure_value: val },
            }
        }

        if (val.toLowerCase().includes('read-write')) {
            return {
                status: 'healthy',
                status_reason: 'MinIO erasure sets report **{{erasure_value}}** — quorum is intact.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { erasure_value: val },
            }
        }

        // Unknown value — report as warning so operators can investigate rather than silently assuming health
        return {
            status: 'warning',
            status_reason: `MinIO erasure health returned an unrecognised value: "${val}".`,
            recommendation: 'Investigate the MinIO erasure health status — the value is not one of the expected "read-write" or "read-only" responses.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { erasure_value: val },
        }
    }
}

export default ErasureHealthChecker
