/**
 * Reports how many SAML identity providers are configured in Cassandra.
 *
 * Pulls the IdP count from Cassandra and checks brig's config to see if
 * SSO is actually enabled. Zero IdPs is only a problem if brig has
 * setSSOEnabled set to true, otherwise it's expected. This catches the
 * JCT-164 situation where spar.issuer_idp is empty even though SSO is
 * turned on in brig.
 */

// External
import yaml from 'js-yaml'

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class CassandraSparIdpCountChecker extends BaseChecker {
    readonly path: string = 'cassandra/spar_idp_count'
    readonly name: string = 'SAML IdP count in Cassandra spar (see: JCT-164)'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Counts **SAML identity providers** configured in Cassandra and cross-references with brig SSO settings. When SSO is enabled but no IdPs exist, users cannot authenticate via SSO and are locked out of Wire.'

    check(data: DataLookup): CheckResult {
        // Auto-detect SSO status from the galley feature flag rather than
        // relying on a user toggle. If galley's SSO flag is not "enabled",
        // this check is not applicable.
        const sso_flag_point = data.get('config/galley_sso_flag')
        if (sso_flag_point?.value) {
            const sso_flag: string = String(sso_flag_point.value).toLowerCase()
            if (!sso_flag.includes('enabled')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'SSO is not enabled in galley (auto-detected). SAML IdP count check does not apply.',
                    display_value: 'skipped (SSO disabled)',
                }
            }
        } else if (data.config && !data.config.options.expect_sso) {
            // Fall back to the user toggle if auto-detection data is unavailable
            return {
                status: 'not_applicable',
                status_reason: 'SSO is not enabled — SAML IdP count check does not apply.',
                display_value: 'skipped',
            }
        }

        const point = data.get('databases/cassandra/spar_idp_count')

        // Couldn't collect the data in the first place
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'SAML IdP count data was not collected from Cassandra spar.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `cqlsh` can query the spar keyspace: `cqlsh -e "SELECT COUNT(*) FROM spar.idp"`\n3. Review the gatherer logs for connection errors or authentication failures',
                recommendation: 'Couldn\'t collect the IdP count from Cassandra spar.',
            }
        }

        const count = parse_number(point)

        // Value wasn't parseable as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'SAML IdP count value from Cassandra spar could not be parsed as a number.',
                recommendation: 'The IdP count from Cassandra spar was not a valid number. Check the raw gatherer output.',
                raw_output: point.raw_output,
            }
        }

        // At least one IdP is set up, so SSO can work
        if (count > 0) {
            return {
                status: 'healthy',
                status_reason: 'Found **{{idp_count}}** SAML IdP(s) configured in Cassandra spar, SSO authentication is available.',
                display_value: count,
                display_unit: 'IdPs',
                raw_output: point.raw_output,
                template_data: { idp_count: count },
            }
        }

        // No IdPs, so we need to check if SSO is actually enabled
        const sso_enabled: boolean | null = this._read_brig_sso_enabled(data)

        if (sso_enabled === true) {
            // Bad news: SSO is on but no IdPs configured, so users are locked out
            return {
                status: 'unhealthy',
                status_reason: 'No SAML IdPs are configured in Cassandra spar, but SSO is **enabled** in brig config, so users cannot authenticate via SSO.',
                fix_hint: '1. Verify the spar IdP table: `cqlsh -e "SELECT * FROM spar.idp"`\n2. Check if the `spar.issuer_idp` table is also empty: `cqlsh -e "SELECT * FROM spar.issuer_idp"`\n3. If IdPs were previously configured, check for data loss or migration issues\n4. To add an IdP, use the Wire admin API or re-run the SAML SSO setup\n5. Alternatively, if SSO is not needed, disable it in brig config: set `setSSOEnabled: false` in the brig ConfigMap',
                recommendation: 'No IdPs in Cassandra spar.idp, but brig has setSSOEnabled turned on. That means users can\'t log in via SSO. Either add an IdP or disable SSO in brig config.',
                display_value: 0,
                display_unit: 'IdPs',
                raw_output: point.raw_output,
            }
        }

        if (sso_enabled === false) {
            // SSO is off, so having zero IdPs is fine
            return {
                status: 'healthy',
                status_reason: 'No SAML IdPs configured, but SSO is **disabled** in brig config, so none are needed.',
                display_value: 0,
                display_unit: 'IdPs',
                raw_output: point.raw_output,
            }
        }

        // Can't reach brig config or the flag isn't there, so we're not sure
        return {
            status: 'warning',
            status_reason: 'No SAML IdPs configured in Cassandra spar, and brig config could not be read to determine if SSO is enabled.',
            fix_hint: '1. Manually check the spar IdP table: `cqlsh -e "SELECT * FROM spar.idp"`\n2. Check brig ConfigMap for `setSSOEnabled`: `kubectl get configmap brig -o yaml | grep setSSOEnabled`\n3. If SSO is enabled and no IdPs exist, users cannot log in via SSO\n4. Either add an IdP via the Wire admin API or disable SSO in brig config',
            recommendation: 'No IdPs in Cassandra spar.idp. Couldn\'t read brig config to check if SSO is enabled. If it is, users won\'t be able to log in via SSO.',
            display_value: 0,
            display_unit: 'IdPs',
            raw_output: point.raw_output,
        }
    }

    /**
     * Pull the setSSOEnabled flag from brig's ConfigMap.
     *
     * @param data all the collected data
     * @returns true or false if we can read it, null if we can't
     */
    private _read_brig_sso_enabled(data: DataLookup): boolean | null {
        const brig_point = data.get('kubernetes/configmaps/brig')

        if (!brig_point?.value) {
            return null
        }

        let parsed: Record<string, unknown>

        try {
            parsed = yaml.load(String(brig_point.value)) as Record<string, unknown>
        } catch {
            return null
        }

        if (!parsed || typeof parsed !== 'object') {
            return null
        }

        const opt_settings = parsed.optSettings as Record<string, unknown> | undefined
        const sso_flag = opt_settings?.setSSOEnabled

        if (typeof sso_flag !== 'boolean') {
            return null
        }

        return sso_flag
    }
}

export default CassandraSparIdpCountChecker
