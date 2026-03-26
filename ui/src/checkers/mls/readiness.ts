/**
 * Checks if MLS (Messaging Layer Security) is ready to go.
 *
 * When MLS is switched on in Galley's feature flags, we verify everything's properly configured:
 *
 * 1. Galley featureFlags.mls status, defaultProtocol, supportedProtocols,
 *    allowedCipherSuites, defaultCipherSuite
 * 2. Galley settings.mlsPrivateKeyPaths all 4 removal key paths need to be there
 * 3. Galley secret all 4 removal key files in the k8s secret
 * 4. Brig optSettings.setEnableMLS can't be explicitly false
 * 5. Brig DPoP settings setDpopMaxSkewSecs, setDpopTokenExpirationTimeSecs
 * 6. Smallstep CA no broken provisioners (only if E2EI is on)
 * 7. Galley featureFlags.mlsE2EId make sure it's consistent when enabled
 *
 * If MLS is off, we just say it's healthy with «MLS not enabled».
 *
 * See https://docs.wire.com/latest/understand/mls.html
 */

// External
import yaml from 'js-yaml'

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import type { DataPoint } from '../../sample-data'
import { type MlsIssue } from './mls_types'
import { check_e2ei_config } from './e2ei_validator'
import { check_brig_mls } from './brig_validator'
import { check_removal_key_paths, check_removal_key_secrets } from './removal_key_validator'

export class MlsReadinessChecker extends BaseChecker {
    readonly path: string = 'mls/readiness'
    readonly name: string = 'MLS readiness (protocol, keys, E2EI)'
    readonly category: string = 'MLS / Protocol'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Validates the full **MLS** (Messaging Layer Security) setup when enabled: feature flags, cipher suites, removal key paths and secrets, brig compatibility, and **E2EI** configuration. Misconfigured MLS prevents end-to-end encrypted group messaging from working and can block message delivery entirely.'

    check(data: DataLookup): CheckResult {
        // Need to parse Galley's config to see if MLS is on
        const galley_point: DataPoint | undefined = data.get('kubernetes/configmaps/galley')
        if (!galley_point) {
            return {
                status: 'gather_failure',
                status_reason: 'Galley ConfigMap data was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has access to the galley ConfigMap: `kubectl get configmap galley -o yaml`\n2. Re-run the gatherer with Kubernetes ConfigMap collection enabled\n3. Check gatherer logs for errors accessing the `galley` ConfigMap',
                recommendation: 'Galley ConfigMap wasn\'t collected. Can\'t assess MLS setup.',
            }
        }

        const galley_yaml: string = String(galley_point.value)
        if (!galley_yaml.trim()) {
            return {
                status: 'gather_failure',
                status_reason: 'Galley ConfigMap value is **empty**.',
                fix_hint: '1. Check the galley ConfigMap directly: `kubectl get configmap galley -o yaml`\n2. If the ConfigMap exists but has no data, the Helm deployment may be misconfigured\n3. Re-run the gatherer to collect the ConfigMap again',
                recommendation: 'Galley ConfigMap is empty. Can\'t check MLS.',
                raw_output: galley_point.raw_output,
            }
        }

        let galley_config: Record<string, unknown>
        try {
            galley_config = yaml.load(galley_yaml) as Record<string, unknown>
        } catch {
            return {
                status: 'warning',
                status_reason: 'Galley ConfigMap YAML could not be parsed.',
                fix_hint: '1. Check the galley ConfigMap for syntax errors: `kubectl get configmap galley -o yaml`\n2. Validate the YAML: pipe the output through a YAML linter\n3. Look for common issues: incorrect indentation, tab characters, or unescaped special characters',
                recommendation: 'Galley YAML is busted. Can\'t check MLS.',
                raw_output: galley_point.raw_output,
            }
        }

        // Dig into the config to find settings.featureFlags.mls
        const settings = galley_config?.settings as Record<string, unknown> | undefined
        const feature_flags = settings?.featureFlags as Record<string, unknown> | undefined
        const mls_flag = feature_flags?.mls as Record<string, unknown> | undefined
        const mls_defaults = mls_flag?.defaults as Record<string, unknown> | undefined
        const mls_status: string = String(mls_defaults?.status ?? 'disabled')

        // MLS off, nothing to check
        if (mls_status !== 'enabled') {
            return {
                status: 'healthy',
                status_reason: 'MLS is **disabled** in Galley (status: `{{mls_status}}`). No MLS configuration needed.',
                display_value: 'MLS not enabled',
                recommendation: 'MLS is disabled in Galley. No setup needed.',
                raw_output: galley_point.raw_output,
                template_data: { mls_status },
            }
        }

        // MLS is enabled, so time to gather all the issues
        const issues: MlsIssue[] = []

        // Check 1: is the MLS feature flag actually configured
        this._check_mls_flag_config(mls_defaults, issues)

        // Check 2: are the removal key paths set up in Galley settings
        check_removal_key_paths(settings, issues)

        // Check 3: do the actual removal key files exist in the k8s secret
        check_removal_key_secrets(data, issues)

        // Check 4: is Brig on board with MLS
        check_brig_mls(data, issues)

        // Check 5: if E2EI is turned on, make sure it's all good
        check_e2ei_config(feature_flags, data, issues)

        // Now assemble the result based on what we found
        const errors: MlsIssue[] = issues.filter((i) => i.severity === 'error')
        const warnings: MlsIssue[] = issues.filter((i) => i.severity === 'warning')

        if (errors.length > 0) {
            const all_messages: string[] = [
                ...errors.map((i) => `ERROR: ${i.message}`),
                ...warnings.map((i) => `WARNING: ${i.message}`),
            ]

            return {
                status: 'unhealthy',
                status_reason: 'MLS is enabled but has **{{error_count}}** error(s) and **{{warning_count}}** warning(s).',
                fix_hint: '1. Check the galley MLS feature flags: `kubectl get configmap galley -o yaml | grep -A 20 "featureFlags"`\n2. Verify removal key paths: `kubectl get configmap galley -o yaml | grep -A 10 "mlsPrivateKeyPaths"`\n3. Check removal key secrets: `kubectl get secret galley -o json | jq ".data | keys"`\n4. Check brig MLS settings: `kubectl get configmap brig -o yaml | grep -E "(setEnableMLS|setDpop)"`\n5. If E2EI is enabled, verify Smallstep CA: `kubectl get configmap smallstep -o yaml`\n6. See the detailed error list in the recommendation below for specific issues to address',
                recommendation: [
                    `MLS is on but there's ${errors.length} error(s) and ${warnings.length} warning(s):`,
                    '',
                    ...all_messages,
                ].join('\n'),
                display_value: `${errors.length} error(s)`,
                raw_output: galley_point.raw_output,
                template_data: {
                    error_count: errors.length,
                    warning_count: warnings.length,
                },
            }
        }

        if (warnings.length > 0) {
            return {
                status: 'warning',
                status_reason: 'MLS is enabled but has **{{warning_count}}** warning(s).',
                fix_hint: '1. Check the galley MLS feature flags: `kubectl get configmap galley -o yaml | grep -A 20 "featureFlags"`\n2. Check brig MLS settings: `kubectl get configmap brig -o yaml | grep -E "(setEnableMLS|setDpop)"`\n3. See the detailed warning list in the recommendation below for specific issues to address',
                recommendation: [
                    `MLS is on but has ${warnings.length} warning(s):`,
                    '',
                    ...warnings.map((i) => `WARNING: ${i.message}`),
                ].join('\n'),
                display_value: `${warnings.length} warning(s)`,
                raw_output: galley_point.raw_output,
                template_data: { warning_count: warnings.length },
            }
        }

        // If we got here, everything checks out. Let's summarize the MLS setup
        const mls_config = mls_defaults?.config as Record<string, unknown> | undefined
        const default_protocol: string = String(mls_config?.defaultProtocol ?? '?')
        const supported: unknown[] = (mls_config?.supportedProtocols as unknown[]) ?? []
        const summary: string = `enabled, default=${default_protocol}, supported=[${supported.join(', ')}]`

        return {
            status: 'healthy',
            status_reason: 'MLS is **enabled** and fully configured: `{{summary}}`.',
            display_value: summary,
            raw_output: galley_point.raw_output,
            template_data: { summary },
        }
    }

    /** Check that the MLS feature flag is properly configured. */
    private _check_mls_flag_config(
        mls_defaults: Record<string, unknown> | undefined,
        issues: MlsIssue[],
    ): void {
        if (!mls_defaults) {
            issues.push({ severity: 'error', message: 'No featureFlags.mls.defaults section in Galley.' })
            return
        }

        const config = mls_defaults.config as Record<string, unknown> | undefined
        if (!config) {
            issues.push({ severity: 'error', message: 'No featureFlags.mls.defaults.config in Galley.' })
            return
        }

        // defaultProtocol needs to be set
        const default_protocol: string = String(config.defaultProtocol ?? '')
        if (!default_protocol) {
            issues.push({ severity: 'error', message: 'mls.config.defaultProtocol is missing.' })
        }

        // supportedProtocols has to have mls in it
        const supported = config.supportedProtocols as unknown[] | undefined
        if (!supported || !Array.isArray(supported)) {
            issues.push({ severity: 'error', message: 'mls.config.supportedProtocols is missing or not an array.' })
        } else if (!supported.includes('mls')) {
            issues.push({ severity: 'error', message: 'mls.config.supportedProtocols doesn\'t include "mls".' })
        }

        // defaultProtocol has to be in the supportedProtocols list
        if (supported && Array.isArray(supported) && default_protocol && !supported.includes(default_protocol)) {
            issues.push({
                severity: 'error',
                message: `defaultProtocol is "${default_protocol}" but that\'s not in supportedProtocols [${supported.join(', ')}].`,
            })
        }

        // allowedCipherSuites has to exist and not be empty
        const cipher_suites = config.allowedCipherSuites as unknown[] | undefined
        if (!cipher_suites || !Array.isArray(cipher_suites) || cipher_suites.length === 0) {
            issues.push({ severity: 'error', message: 'mls.config.allowedCipherSuites is missing or empty.' })
        }

        // defaultCipherSuite must be set and must be in the allowed list
        const default_suite = config.defaultCipherSuite
        if (default_suite === undefined || default_suite === null) {
            issues.push({ severity: 'error', message: 'mls.config.defaultCipherSuite is missing.' })
        } else if (cipher_suites && Array.isArray(cipher_suites) && !cipher_suites.includes(default_suite)) {
            issues.push({
                severity: 'error',
                message: `defaultCipherSuite (${default_suite}) isn\'t in allowedCipherSuites [${cipher_suites.join(', ')}].`,
            })
        }
    }

}

export default MlsReadinessChecker
