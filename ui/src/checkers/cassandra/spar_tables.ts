/**
 * Checks that the Cassandra spar keyspace has the required schema tables.
 *
 * Consumes the databases/cassandra/spar_tables target (boolean). If any of
 * the tables (idp, issuer_idp, user, bind) are missing, SAML SSO configuration
 * can't be persisted and SSO logins will fail. See JCT-164.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class CassandraSparTablesChecker extends BaseChecker {
    readonly path: string = 'cassandra/spar_tables'
    readonly name: string = 'Cassandra spar keyspace schema (see: JCT-164)'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Checks that the Cassandra `spar` keyspace contains all required schema tables (`idp`, `issuer_idp`, `user`, `bind`). Missing tables prevent **SAML SSO** configuration from being persisted, breaking SSO logins for Wire users.'

    check(data: DataLookup): CheckResult {
        // Auto-detect SSO status from galley feature flag
        const sso_flag_point = data.get('config/galley_sso_flag')
        if (sso_flag_point?.value) {
            const sso_flag: string = String(sso_flag_point.value).toLowerCase()
            if (!sso_flag.includes('enabled')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'SSO is not enabled in galley (auto-detected). Spar table schema check does not apply.',
                    display_value: 'skipped (SSO disabled)',
                }
            }
        } else if (data.config && !data.config.options.expect_sso) {
            return {
                status: 'not_applicable',
                status_reason: 'SSO is not enabled — spar table schema check does not apply.',
                display_value: 'skipped',
            }
        }

        const point = data.get('databases/cassandra/spar_tables')

        // No data collected for this check
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra spar table schema data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `cqlsh` can connect and query the `spar` keyspace: `cqlsh -e "DESCRIBE TABLES IN spar"`\n3. Review the gatherer logs for connection errors or authentication failures',
                recommendation: 'Cassandra spar table schema data not collected.',
            }
        }

        // Null value means the collector ran but the command failed to return usable data
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra spar table schema check returned null — the command likely failed during collection.',
                recommendation: 'Cassandra spar table schema data could not be collected. Check SSH access and Cassandra connectivity.',
                raw_output: point.raw_output,
            }
        }

        const val: boolean | string | number = point.value as boolean | string | number

        // All required tables are there
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All required spar schema tables (`idp`, `issuer_idp`, `user`, `bind`) are present in Cassandra.',
                display_value: 'all tables present',
                raw_output: point.raw_output,
            }
        }

        // One or more tables missing
        if (val === false) {
            // Try to grab which specific tables are missing from the collector's health_info.
            // We cast here to work around some stale TS caching on DataPoint.metadata.
            // Format looks like «Missing spar tables: bind» or «Missing spar tables: idp, bind»
            const health_info: string = (point as { metadata?: { health_info?: string } }).metadata?.health_info ?? ''
            const missing_match: RegExpMatchArray | null = health_info.match(/Missing spar tables:\s*(.+)/)
            const missing_tables: string = missing_match?.[1] ?? 'idp, issuer_idp, user, bind'

            return {
                status: 'unhealthy',
                status_reason: 'Cassandra spar keyspace is missing required table(s): **{{missing_tables}}**.',
                fix_hint: '1. List existing tables in the spar keyspace: `cqlsh -e "DESCRIBE TABLES IN spar"`\n2. The missing table(s) **{{missing_tables}}** are created by the spar schema migration\n3. Re-run the spar schema migration: check the Wire deployment docs for `spar-migrate-data` or the Helm chart `spar` migration job\n4. Verify spar service logs for migration errors: `kubectl logs <spar_pod> | grep -i "migration\\|schema\\|table"`',
                recommendation: `Cassandra spar table(s) missing: ${missing_tables}. SAML SSO configuration won't work until you run the spar schema migration.`,
                display_value: `missing: ${missing_tables}`,
                raw_output: point.raw_output,
                template_data: { missing_tables },
            }
        }

        // Got something unexpected, just show it
        return {
            status: 'warning',
            status_reason: 'Received unexpected value **{{unexpected_value}}** from the spar table check; cannot determine table presence.',
            fix_hint: '1. Manually verify spar tables exist: `cqlsh -e "DESCRIBE TABLES IN spar"`\n2. Expected tables: `idp`, `issuer_idp`, `user`, `bind`\n3. If tables are missing, re-run the spar schema migration',
            recommendation: 'Unexpected value from Cassandra spar table check.',
            display_value: String(val),
            raw_output: point.raw_output,
            template_data: { unexpected_value: String(val) },
        }
    }
}

export default CassandraSparTablesChecker
