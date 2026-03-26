/**
 * Checks Brig's MLS config to make sure it's set right.
 *
 * Things we verify:
 * setEnableMLS isn't explicitly false (or MLS endpoints break)
 * DPoP settings are there (setDpopMaxSkewSecs, setDpopTokenExpirationTimeSecs)
 *
 * Note: OAuth stuff (setOAuthEnabled) is in e2ei_validator.ts since that
 * matters for E2EI, not MLS directly.
 *
 * Split out separately because Brig config is its own thing in Kubernetes
 * and doesn't pull from Galley like the main MLS check does.
 */

// External
import yaml from 'js-yaml'

// Ours
import type { DataLookup } from '../data_lookup'
import type { DataPoint } from '../../sample-data'
import type { MlsIssue } from './mls_types'

/**
 * Fetch Brig's config, parse it, and validate the MLS settings.
 * Anything wrong goes into the issues list.
 *
 * @param data   DataLookup to pull Brig config from
 * @param issues Array where we stash problems we find
 */
export function check_brig_mls(
    data: DataLookup,
    issues: MlsIssue[],
): void {
    // Get Brig config and bail if it's not there
    const brig_point: DataPoint | undefined = data.get('kubernetes/configmaps/brig')
    if (!brig_point) {
        issues.push({
            severity: 'warning',
            message: 'Brig ConfigMap wasn\'t collected. Can\'t check if MLS is enabled.',
        })
        return
    }

    const brig_yaml: string = String(brig_point.value)
    if (!brig_yaml.trim()) return

    let brig_config: unknown
    try {
        brig_config = yaml.load(brig_yaml)
    } catch {
        return
    }

    // yaml.load can return null for empty documents, need to guard against that
    if (!brig_config || typeof brig_config !== 'object') {
        issues.push({
            severity: 'warning',
            message: 'Brig YAML is empty or invalid. Can\'t check the MLS settings.',
        })
        return
    }

    const opt_settings = (brig_config as Record<string, unknown>).optSettings as Record<string, unknown> | undefined
    if (!opt_settings) {
        issues.push({
            severity: 'warning',
            message: 'No optSettings section in Brig config.',
        })
        return
    }

    // setEnableMLS only breaks things if explicitly set to false.
    // If missing, Brig just does what Galley wants, which is fine.
    if ('setEnableMLS' in opt_settings && opt_settings.setEnableMLS === false) {
        issues.push({
            severity: 'error',
            message: 'Brig has setEnableMLS explicitly false. That kills the MLS endpoints.',
        })
    }

    // DPoP settings are required for E2EI and good practice
    if (!opt_settings.setDpopMaxSkewSecs && opt_settings.setDpopMaxSkewSecs !== 0) {
        issues.push({
            severity: 'warning',
            message: 'Brig setDpopMaxSkewSecs is missing (E2EI/MLS DPoP validation needs this).',
        })
    }

    if (!opt_settings.setDpopTokenExpirationTimeSecs && opt_settings.setDpopTokenExpirationTimeSecs !== 0) {
        issues.push({
            severity: 'warning',
            message: 'Brig setDpopTokenExpirationTimeSecs is missing (E2EI/MLS DPoP validation needs this).',
        })
    }

}
