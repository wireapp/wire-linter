/**
 * Checks MinIO's version and warns if it's getting old.
 *
 * Uses the databases/minio/version metric. MinIO dates its versions
 * (like «2023-07-07T07:13:57Z»). If it's more than 18 months old,
 * you're probably missing security patches.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// How many days until we say «this is too old»
const MAX_AGE_DAYS: number = 548  // roughly 18 months

/**
 * Take a MinIO version string and convert it to a Date.
 * MinIO versions are formatted as ISO dates like «2023-07-07T07:13:57Z».
 */
function parse_minio_version_date(version: string): Date | null {
    // Try parsing directly as ISO date
    const parsed: number = Date.parse(version)
    if (!isNaN(parsed)) {
        return new Date(parsed)
    }

    // Try extracting a date pattern from the string
    const match = version.match(/(\d{4})-(\d{2})-(\d{2})/)
    if (match) {
        return new Date(`${match[1]}-${match[2]}-${match[3]}`)
    }

    return null
}

export class VersionChecker extends BaseChecker {
    readonly path: string = 'minio/version'
    readonly name: string = 'MinIO version'
    readonly category: string = 'Data / MinIO'
    readonly interest = 'Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Identifies the installed **MinIO version** and flags releases older than **18 months**. Outdated versions miss security patches and bug fixes that protect stored files and assets.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/minio/version')

        // No version data collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO version data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the MinIO host\n2. Check that `mc admin info <alias>` returns version information\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'MinIO version data not available.',
            }
        }

        const version: string = String(point.value)
        const version_date: Date | null = parse_minio_version_date(version)

        // Couldn't parse the date, so just show the raw version
        if (!version_date) {
            return {
                status: 'healthy',
                status_reason: 'MinIO version is `{{version}}` (unable to determine age from version string).',
                display_value: version,
                raw_output: point.raw_output,
                template_data: { version },
            }
        }

        // Figure out how old this version is
        const now: Date = new Date()
        const age_ms: number = now.getTime() - version_date.getTime()
        const age_days: number = Math.floor(age_ms / (1000 * 60 * 60 * 24))

        if (age_days > MAX_AGE_DAYS) {
            const age_months: number = Math.floor(age_days / 30)
            return {
                status: 'warning',
                status_reason: 'MinIO version `{{version}}` is approximately **{{age_months}} months** old, exceeding the **18-month** threshold.',
                fix_hint: '1. Check the current MinIO version: `mc admin info <alias>`\n2. Review the [MinIO release notes](https://github.com/minio/minio/releases) for security fixes\n3. Plan an upgrade following the MinIO upgrade procedure: `mc admin update <alias>`\n4. After upgrading, verify the cluster is healthy: `mc admin info <alias>`',
                recommendation: `MinIO version is ~${age_months} months old (${version}). This old, you're probably missing security patches. Worth upgrading.`,
                display_value: `${version} (~${age_months}mo old)`,
                raw_output: point.raw_output,
                template_data: { version, age_months },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'MinIO version `{{version}}` is **{{age_months}} months** old, within the **18-month** acceptable window.',
            display_value: version,
            raw_output: point.raw_output,
            template_data: { version, age_months: Math.floor(age_days / 30) },
        }
    }
}

export default VersionChecker
