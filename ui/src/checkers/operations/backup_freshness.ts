/**
 * Checks whether backups are fresh and not stale.
 *
 * Consumes the operations/backup_freshness target (boolean or string).
 * Stale backups mean the backup job failed silently. You're left without
 * a recovery point if something goes wrong.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class BackupFreshnessChecker extends BaseChecker {
    readonly path: string = 'operations/backup_freshness'
    readonly name: string = 'Backup freshness'
    readonly category: string = 'Operations / Tooling'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Monitors whether backups are **recent** and not stale. Stale backups indicate a silently failing backup job, leaving **no recovery point** if data loss occurs.'

    check(data: DataLookup): CheckResult {
        const point = data.get('operations/backup_freshness')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `operations/backup_freshness` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has **SSH access** to the backup host\n2. Check that the backup storage location is mounted and accessible\n3. Review the gatherer logs for permission errors or path issues',
                recommendation: 'Backup freshness data not collected.',
            }
        }

        // Null value means the gatherer command failed — not the same as stale backups
        if (point.value === null || point.value === undefined) {
            return {
                status: 'gather_failure',
                status_reason: 'Backup freshness data was collected but the value is null.',
                recommendation: (point.metadata?.error as string) ?? 'Backup freshness target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean
        // The gatherer populates health_info with a structured assessment like
        // "Recent backup files found (< 1 hour old)" or "No backup files newer than 1 hour found"
        const health_info: string = (point.metadata?.health_info as string) ?? ''
        const base_recommendation: string = 'Backups are stale or missing. The backup job may have failed silently.'
        const recommendation: string = health_info
            ? `${base_recommendation} ${health_info}.`
            : base_recommendation

        // String value — use health_info to determine actual status rather than
        // assuming any non-empty string means healthy
        if (typeof val === 'string') {
            // health_info starting with "Recent" indicates the gatherer confirmed fresh backups
            if (health_info.toLowerCase().startsWith('recent')) {
                return {
                    status: 'healthy',
                    status_reason: 'Backups are **fresh**: {{detail}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { detail: val },
                }
            }

            // No health_info and empty value — no data at all
            if (val.length === 0) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Backups are stale or missing; the backup job may have failed silently.',
                    recommendation,
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Non-empty string but health_info does not confirm freshness —
            // the value could be an error message, "old or missing", "no backups found", etc.
            return {
                status: 'unhealthy',
                status_reason: `Backup check returned: ${val}.`,
                recommendation,
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true means backups are fresh
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Backups are **fresh** and within the expected retention window.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false backups are stale
        return {
            status: 'unhealthy',
            status_reason: 'Backups are stale or missing; the backup job may have failed silently.',
            recommendation,
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default BackupFreshnessChecker
