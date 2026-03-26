/**
 * MLS removal key validators.
 *
 * Validates the removal key configuration from both angles:
 *   check_removal_key_paths: checks that Galley settings declare all 4
 *     removal key algorithm paths under mlsPrivateKeyPaths.removal.
 *   check_removal_key_secrets: checks the k8s Galley secret actually
 *     has the corresponding .pem files for each removal key.
 *
 * Both functions reference REQUIRED_REMOVAL_KEY_ALGORITHMS and
 * REQUIRED_REMOVAL_SECRET_KEYS from mls_types.
 */

// Ours
import type { DataLookup } from '../data_lookup'
import type { DataPoint } from '../../sample-data'
import { REQUIRED_REMOVAL_KEY_ALGORITHMS, REQUIRED_REMOVAL_SECRET_KEYS, type MlsIssue } from './mls_types'

/** Check that all 4 MLS removal key paths are configured in Galley settings. */
export function check_removal_key_paths(
    settings: Record<string, unknown> | undefined,
    issues: MlsIssue[],
): void {
    const key_paths = settings?.mlsPrivateKeyPaths as Record<string, unknown> | undefined
    const removal = key_paths?.removal as Record<string, unknown> | undefined

    if (!removal) {
        issues.push({
            severity: 'error',
            message: 'settings.mlsPrivateKeyPaths.removal is missing. All 4 removal key algorithms are required for MLS.',
        })
        return
    }

    for (const algo of REQUIRED_REMOVAL_KEY_ALGORITHMS) {
        if (!removal[algo]) {
            issues.push({
                severity: 'error',
                message: `Removal key path for "${algo}" is missing in settings.mlsPrivateKeyPaths.removal.`,
            })
        }
    }
}

/** Check that the Galley k8s secret contains the actual removal key files. */
export function check_removal_key_secrets(
    data: DataLookup,
    issues: MlsIssue[],
): void {
    // The secrets checker collects all secrets, so we dig through the raw output
    // to find the galley secret and what keys it has
    const secrets_point: DataPoint | undefined = data.get('secrets/required_present')
    if (!secrets_point || !secrets_point.raw_output) {
        issues.push({
            severity: 'warning',
            message: 'Galley k8s secret data not available - can\'t verify removal key files exist.',
        })
        return
    }

    // Parse the raw output: JSON containing all k8s secrets
    let secrets_data: Record<string, unknown>
    try {
        secrets_data = JSON.parse(secrets_point.raw_output) as Record<string, unknown>
    } catch {
        return
    }

    const items = secrets_data.items as Array<Record<string, unknown>> | undefined
    if (!items) return

    // Find which one is the galley secret
    const galley_secret = items.find((item) => {
        const name: string = (item.metadata as Record<string, unknown>)?.name as string ?? ''
        return name === 'galley'
    })

    if (!galley_secret) {
        issues.push({
            severity: 'warning',
            message: 'Galley k8s secret not found - can\'t verify removal key files exist.',
        })
        return
    }

    const secret_keys: string[] = Object.keys((galley_secret.data as Record<string, unknown>) ?? {})

    for (const required_key of REQUIRED_REMOVAL_SECRET_KEYS) {
        if (!secret_keys.includes(required_key)) {
            issues.push({
                severity: 'error',
                message: `Galley secret missing removal key file: ${required_key}`,
            })
        }
    }
}
