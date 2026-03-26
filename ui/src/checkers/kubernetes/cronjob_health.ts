/**
 * Checks CronJob health — flags failed or suspended CronJobs.
 *
 * CronJobs handle backups, certificate rotation, and other periodic
 * tasks. A silently failing CronJob can go unnoticed for weeks.
 *
 * Consumes: kubernetes/cronjobs/health
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class CronJobHealthChecker extends BaseChecker {
    readonly path: string = 'kubernetes/cronjob_health'
    readonly name: string = 'CronJob health'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly data_path: string = 'kubernetes/cronjobs/health'
    readonly explanation: string =
        '**CronJobs** handle periodic tasks like backups and certificate rotation. A silently ' +
        'failing CronJob can go unnoticed for weeks until the backup is actually needed or ' +
        'a certificate expires.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const point = data.get('kubernetes/cronjobs/health')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'CronJob health data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            cronjob_count?: number
            cronjobs?: {
                name: string
                schedule: string
                suspended: boolean
                last_schedule: string | null
                last_job_status: string | null
                last_job_name: string | null
            }[]
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse CronJob data.', raw_output: point.raw_output }
        }

        const cronjob_count: number = parsed.cronjob_count ?? 0
        const cronjobs = parsed.cronjobs ?? []

        if (cronjob_count === 0) {
            return {
                status: 'healthy',
                status_reason: 'No CronJobs found in the Wire namespace.',
                display_value: 'none',
                raw_output: point.raw_output,
                template_data: { failed_names: [] },
            }
        }

        // Check for issues
        const failed = cronjobs.filter(
            (cj: { last_job_status: string | null }) => cj.last_job_status === 'failed'
        )
        const suspended = cronjobs.filter(
            (cj: { suspended: boolean }) => cj.suspended
        )
        const never_run = cronjobs.filter(
            (cj: { last_schedule: string | null; suspended: boolean }) =>
                !cj.last_schedule && !cj.suspended
        )

        const issues: string[] = []

        if (failed.length > 0) {
            const names: string = failed.map((cj: { name: string }) => `**${cj.name}**`).join(', ')
            issues.push(`${failed.length} failed: ${names}`)
        }

        if (suspended.length > 0) {
            const names: string = suspended.map((cj: { name: string }) => `**${cj.name}**`).join(', ')
            issues.push(`${suspended.length} suspended: ${names}`)
        }

        if (never_run.length > 0) {
            const names: string = never_run.map((cj: { name: string }) => `**${cj.name}**`).join(', ')
            issues.push(`${never_run.length} never ran: ${names}`)
        }

        if (failed.length > 0) {
            // Pre-render kubectl commands to avoid passing external names through Handlebars {{each}},
            // which would be an injection vector if a CronJob name contained Handlebars expressions
            const job_commands: string = failed
                .map((cj: { name: string }) =>
                    `# Find the most recent Job for CronJob "${cj.name}":\n` +
                    `kubectl get jobs -n ${ns} --sort-by=.metadata.creationTimestamp | grep -F '${cj.name}'\n` +
                    `# Then check its logs:\n` +
                    `# kubectl logs job/<job-name-from-above> -n ${ns}`)
                .join('\n')

            return {
                status: 'warning',
                status_reason: `CronJob issues: ${issues.join('; ')}.`,
                fix_hint: 'Check failed CronJob logs:\n```\n{{{job_commands}}}\n```\nAlso check:\n```\nkubectl describe cronjob -n {{ns}}\n```',
                display_value: `${failed.length} failed`,
                raw_output: point.raw_output,
                template_data: { job_commands, ns },
            }
        }

        if (issues.length > 0) {
            return {
                status: 'warning',
                status_reason: `CronJob issues: ${issues.join('; ')}.`,
                fix_hint: 'Review CronJob status:\n```\nkubectl get cronjobs -n {{ns}}\nkubectl describe cronjob -n {{ns}}\n```',
                display_value: `${issues.length} issue(s)`,
                raw_output: point.raw_output,
                template_data: { ns },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All ${cronjob_count} CronJob(s) operating normally.`,
            display_value: `${cronjob_count} OK`,
            raw_output: point.raw_output,
            template_data: { failed_names: [] },
        }
    }
}

export default CronJobHealthChecker
