/**
 * Reports on LDAP-SCIM bridge CronJob status (auto-detected).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class LdapScimBridgeChecker extends BaseChecker {
    readonly path: string = 'wire_services/ldap_scim_bridge'
    readonly name: string = 'LDAP-SCIM bridge'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'The LDAP-SCIM bridge synchronizes users from Active Directory/LDAP into Wire via the SCIM API. Deployed as a Kubernetes CronJob (one per team).'

    check(data: DataLookup): CheckResult {
        const point = data.get('wire_services/ldap_scim_bridge_status')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'LDAP-SCIM bridge status not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const count: number = (parsed.cronjobs_found as number) ?? 0
        if (count === 0) {
            return { status: 'healthy', status_reason: 'No LDAP-SCIM bridges found in the cluster. (This is normal if LDAP sync is not used.)', display_value: 'none found' }
        }

        const cronjobs: Array<Record<string, unknown>> = (parsed.cronjobs as Array<Record<string, unknown>>) ?? []
        const failed: Array<Record<string, unknown>> = cronjobs.filter(c => c.last_job_succeeded === false)

        if (failed.length > 0) {
            const names: string = failed.map(c => `\`${c.name}\``).join(', ')
            return {
                status: 'warning',
                status_reason: `**${count}** LDAP-SCIM bridge(s) found, but **${failed.length}** had failed last runs: ${names}. User sync may be stale.`,
                fix_hint: 'Check bridge logs:\n```\nkubectl logs job/<latest-job> -n wire\n```',
                display_value: `${count} bridge(s), ${failed.length} failed`,
                raw_output: point.raw_output,
            }
        }

        const names: string = cronjobs.map(c => `\`${c.name}\``).join(', ')
        return { status: 'healthy', status_reason: `**${count}** LDAP-SCIM bridge(s) found and healthy: ${names}.`, display_value: `${count} bridge(s)`, raw_output: point.raw_output }
    }
}

export default LdapScimBridgeChecker
