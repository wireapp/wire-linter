/**
 * Checks whether all required Cassandra keyspaces exist.
 *
 * Consumes the databases/cassandra/keyspaces target. The value is either
 * boolean true (all keyspaces present), boolean false (some missing), or
 * a string listing the keyspaces found. The four required keyspaces
 * (brig, galley, spar, gundeck) map 1:1 to Wire backend services.
 * If a keyspace is missing, that service won't work at all.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// Wire backend services that each need their own Cassandra keyspace
const REQUIRED_KEYSPACES: readonly string[] = ['brig', 'galley', 'spar', 'gundeck']

export class KeyspacesChecker extends BaseChecker {
    readonly path: string = 'cassandra/keyspaces'
    readonly name: string = 'Required keyspaces exist'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Validates that all four required Cassandra keyspaces (`brig`, `galley`, `spar`, `gundeck`) exist. Each keyspace maps to a Wire backend service, and a missing keyspace prevents that service from starting.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/cassandra/keyspaces')

        // Couldn't get the keyspace data from the collector
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra keyspace data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `cqlsh` is accessible and can run: `cqlsh -e "DESCRIBE KEYSPACES"`\n3. Review the gatherer logs for connection errors or authentication failures',
                recommendation: 'Required keyspaces exist data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra keyspace data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Keyspace target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // All keyspaces are there
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All required Cassandra keyspaces (`brig`, `galley`, `spar`, `gundeck`) are present.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Some keyspaces are missing
        if (val === false) {
            return {
                status: 'unhealthy',
                status_reason: 'One or more required Cassandra keyspaces (`brig`, `galley`, `spar`, `gundeck`) are missing.',
                fix_hint: '1. List existing keyspaces: `cqlsh -e "DESCRIBE KEYSPACES"`\n2. Identify which of `brig`, `galley`, `spar`, `gundeck` are missing\n3. Missing keyspaces are created by the Wire backend services during initial setup; re-run the Helm chart installation or schema migration for the affected service\n4. Verify Cassandra connectivity from the Wire service pods: `kubectl logs <pod_name> | grep -i cassandra`',
                recommendation: 'One or more required Cassandra keyspaces are missing (brig, galley, spar, gundeck). If a keyspace is missing, the corresponding service won\'t work.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Got a list of keyspaces, need to check if all required ones are in there
        if (typeof val === 'string') {
            const lower: string = val.toLowerCase()
            const missing: string[] = REQUIRED_KEYSPACES.filter(
                (ks: string) => !new RegExp('\\b' + ks + '\\b').test(lower)
            )

            if (missing.length > 0) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Missing required Cassandra keyspaces: **{{missing_keyspaces}}**.',
                    fix_hint: '1. Verify current keyspaces: `cqlsh -e "DESCRIBE KEYSPACES"`\n2. The missing keyspace(s) **{{missing_keyspaces}}** must be created by the corresponding Wire backend service\n3. Re-run the Helm chart installation or schema migration for the affected service(s)\n4. Check service logs for schema migration errors: `kubectl logs <service_pod> | grep -i "schema\\|migration\\|keyspace"`',
                    recommendation: `Missing required keyspaces: ${missing.join(', ')}. Each missing keyspace means that service won't start up properly.`,
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { missing_keyspaces: missing.join(', ') },
                }
            }

            // Found all the required keyspaces
            return {
                status: 'healthy',
                status_reason: 'All required Cassandra keyspaces (`brig`, `galley`, `spar`, `gundeck`) were found.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Got something unexpected — cannot verify keyspace presence, so warn rather than assume healthy
        return {
            status: 'warning',
            status_reason: `Cassandra keyspace check returned an unexpected value type (${typeof val}).`,
            recommendation: 'Cassandra keyspace check returned an unexpected value type. Re-run the gatherer and verify keyspaces manually.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default KeyspacesChecker
