/**
 * Checks whether MinIO's drives are online or offline.
 *
 * Uses the databases/minio/drives_status metric (something like «6/6 online»).
 * If any go dark, you're risking data loss or the whole thing going down.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class DrivesStatusChecker extends BaseChecker {
    readonly path: string = 'minio/drives_status'
    readonly name: string = 'Drives status (online/offline)'
    readonly category: string = 'Data / MinIO'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Ensures all **MinIO storage drives** are online. Offline drives reduce **storage redundancy** and can lead to data loss or service unavailability for file uploads and assets.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/minio/drives_status')

        // No drive data available
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO drives status data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the MinIO host\n2. Check that `mc admin info <alias>` returns drive information\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'No drives status data.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO drives status data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Drives status target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string = String(point.value)

        // Pull the offline drive count out of whatever format it comes in as
        const offline_match = val.match(/(\d+)\s*(?:drives?\s*)?offline/i)
        const offline_count = offline_match?.[1] !== undefined ? parseInt(offline_match[1], 10) : 0
        if (offline_count > 0) {
            return {
                status: 'unhealthy',
                status_reason: '**{{offline_count}}** MinIO drive(s) are offline ({{drives_value}}).',
                fix_hint: '1. Check drive status: `mc admin info <alias>`\n2. Inspect disk health on the affected nodes: `lsblk` and `smartctl -a /dev/<disk>`\n3. Check MinIO logs for I/O errors: `journalctl -u minio` or `kubectl logs <minio_pod>`\n4. If a drive has failed, replace it and run: `mc admin heal -r <alias>`\n5. Verify mount points are accessible: `df -h` on the MinIO host',
                recommendation: 'Some of MinIO\'s drives are down. That\'s not good.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { offline_count, drives_value: val },
            }
        }

        // Detect M/N ratio formats like "4/6 online" or "6/6 OK" from the gatherer
        const ratio_match = val.match(/(\d+)\s*\/\s*(\d+)\s*(?:online|OK)/i)
        if (ratio_match?.[1] !== undefined && ratio_match[2] !== undefined) {
            const online = parseInt(ratio_match[1], 10)
            const total  = parseInt(ratio_match[2], 10)

            // Some drives are not reporting as online
            if (online < total) {
                const down = total - online
                return {
                    status: 'unhealthy',
                    status_reason: `${down} of ${total} MinIO drive(s) are not online (${val}).`,
                    recommendation: 'Some of MinIO\'s drives are down. That\'s not good.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // All drives accounted for and online
            return {
                status: 'healthy',
                status_reason: `All ${total} MinIO drives are online (${val}).`,
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Format was not recognized — neither an offline count nor an N/M ratio was found.
        // Returning healthy here would be a false positive; surface this as a warning instead.
        return {
            status: 'warning',
            status_reason: `MinIO drives status format not recognized: "${val}".`,
            recommendation: 'The drives status value could not be parsed. Verify the MinIO installation and re-run the gatherer.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { drives_value: val },
        }
    }
}

export default DrivesStatusChecker
