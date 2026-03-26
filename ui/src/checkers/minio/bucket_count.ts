/**
 * Shows how many buckets you have in MinIO.
 *
 * Uses the databases/minio/bucket_count metric. Just a heads up on what's
 * there no judgment, always green.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class BucketCountChecker extends BaseChecker {
    readonly path: string = 'minio/bucket_count'
    readonly name: string = 'Bucket count'
    readonly category: string = 'Data / MinIO'
    readonly interest = 'Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Reports the number of **S3 buckets** configured in MinIO. Provides a quick inventory of the object storage layout used by Wire for file uploads, assets, and other blob data.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/minio/bucket_count')

        // Couldn't gather bucket data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO bucket count data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the MinIO host\n2. Check that `mc ls <alias>` returns bucket listings\n3. Review the gatherer logs for connection or authentication errors',
                recommendation: 'No bucket count data yet.',
            }
        }

        const count = parse_number(point)

        // Value could not be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO bucket count value could not be parsed as a number.',
                recommendation: 'The collected bucket count data was not in a recognizable numeric format.',
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'MinIO has **{{count}}** bucket(s) configured.',
            display_value: count,
            display_unit: 'buckets',
            raw_output: point.raw_output,
            template_data: { count },
        }
    }
}

export default BucketCountChecker
