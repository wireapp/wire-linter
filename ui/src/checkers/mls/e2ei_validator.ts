/**
 * E2EI (End-to-End Identity) validator for MLS setup.
 *
 * Checks the mlsE2EId feature flag and makes sure its config actually works
 * when you turn it on. Things we verify:
 *
 * mlsE2EId has acmeDiscoveryUrl and verificationExpiration set up right
 * Smallstep CA configmap exists and is healthy
 * Provisioners are working (no broken ones, at least one exists)
 *
 * Split out from the main MLS checker since E2EI pulls from different
 * places (feature flags + Smallstep configmap) and will probably get
 * more complex as we go.
 */

// External
import yaml from 'js-yaml'

// Ours
import type { DataLookup } from '../data_lookup'
import type { DataPoint } from '../../sample-data'
import type { MlsIssue } from './mls_types'

/**
 * Validates E2EI config when it's turned on.
 *
 * Looks at the mlsE2EId feature flag, and if it's enabled, checks that the
 * config looks good and Smallstep CA is actually there and working.
 *
 * @param feature_flags Parsed Galley feature flags
 * @param data          DataLookup to grab other configmaps
 * @param issues        List we throw problems into
 */
export function check_e2ei_config(
    feature_flags: Record<string, unknown> | undefined,
    data: DataLookup,
    issues: MlsIssue[],
): void {
    if (!feature_flags) return

    const e2ei_flag = feature_flags.mlsE2EId as Record<string, unknown> | undefined
    const e2ei_defaults = e2ei_flag?.defaults as Record<string, unknown> | undefined
    const e2ei_status: string = String(e2ei_defaults?.status ?? 'disabled')

    // If E2EI is off, we're done here
    if (e2ei_status !== 'enabled') return

    // E2EI needs OAuth to work, so check if Brig has that enabled
    const brig_point: DataPoint | undefined = data.get('kubernetes/configmaps/brig')
    if (brig_point) {
        const brig_yaml: string = String(brig_point.value)
        if (brig_yaml.trim()) {
            try {
                const brig_config = yaml.load(brig_yaml)
                // yaml.load can give us null for empty YAML, so we guard before accessing properties
                if (brig_config && typeof brig_config === 'object') {
                    const opt_settings = (brig_config as Record<string, unknown>).optSettings as Record<string, unknown> | undefined
                    if (opt_settings && opt_settings.setOAuthEnabled === false) {
                        issues.push({
                            severity: 'warning',
                            message: 'Brig has OAuth turned off, but E2EI needs it on.',
                        })
                    }
                }
            } catch {
                // Brig validator will flag YAML issues if there are any
            }
        }
    }

    // Now verify the E2EI config itself
    const e2ei_config = e2ei_defaults?.config as Record<string, unknown> | undefined

    if (!e2ei_config) {
        issues.push({
            severity: 'error',
            message: 'E2EI is on but there\'s no config section.',
        })
        return
    }

    // Need an ACME discovery URL to talk to Smallstep
    if (!e2ei_config.acmeDiscoveryUrl) {
        issues.push({
            severity: 'error',
            message: 'E2EI is on but acmeDiscoveryUrl is missing. Without it, we can\'t reach Smallstep.',
        })
    }

    // verificationExpiration isn't strictly required since it has a default
    if (!e2ei_config.verificationExpiration) {
        issues.push({
            severity: 'warning',
            message: 'E2EI verification expiration isn\'t set (will use 86400s, which is 1 day).',
        })
    }

    // Smallstep needs to be there and working
    const smallstep_point: DataPoint | undefined = data.get('kubernetes/configmaps/smallstep')
    if (!smallstep_point) {
        issues.push({
            severity: 'warning',
            message: 'Smallstep CA data wasn\'t collected, so we can\'t check if it\'s healthy.',
        })
        return
    }

    // Parse the Smallstep config and check for issues
    const smallstep_json: string = String(smallstep_point.value)
    if (!smallstep_json.trim()) {
        // No config means no provisioners, which means cert issuance is gonna fail
        issues.push({
            severity: 'warning',
            message: 'Smallstep CA ConfigMap is empty. Can\'t verify if provisioners are set up.',
        })
    } else {
        try {
            const smallstep_config = JSON.parse(smallstep_json) as Record<string, unknown>
            const authority = smallstep_config?.authority as Record<string, unknown> | undefined
            const provisioners = authority?.provisioners as Array<Record<string, unknown>> | undefined

            if (Array.isArray(provisioners)) {
                const broken_count: number = provisioners.filter(
                    (p) => p && typeof p === 'object' && 'Error' in p,
                ).length

                if (broken_count > 0) {
                    issues.push({
                        severity: 'error',
                        message: `Smallstep has ${broken_count} broken provisioner(s). Certificate issuance won't work.`,
                    })
                }
            }

            if (!provisioners || provisioners.length === 0) {
                issues.push({
                    severity: 'error',
                    message: 'Smallstep CA has no provisioners. E2EI cert issuance will fail.',
                })
            }
        } catch {
            issues.push({
                severity: 'warning',
                message: 'Smallstep CA ConfigMap has invalid JSON. Can\'t parse the config.',
            })
        }
    }
}
