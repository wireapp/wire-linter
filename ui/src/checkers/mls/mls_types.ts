/**
 * Shared MLS types and constants across all the sub-validators.
 *
 * Has the removal key algorithm IDs, their secret key filenames, and the
 * MlsIssue interface for reporting problems with severity levels. One place
 * for everything so we don't create circular dependencies everywhere.
 */

// The four algorithms MLS removal keys use
export const REQUIRED_REMOVAL_KEY_ALGORITHMS: string[] = [
    'ed25519',
    'ecdsa_secp256r1_sha256',
    'ecdsa_secp384r1_sha384',
    'ecdsa_secp521r1_sha512',
]

// The secret key file names we're looking for
export const REQUIRED_REMOVAL_SECRET_KEYS: string[] = [
    'removal_ed25519.pem',
    'removal_ecdsa_secp256r1_sha256.pem',
    'removal_ecdsa_secp384r1_sha384.pem',
    'removal_ecdsa_secp521r1_sha512.pem',
]

export interface MlsIssue {
    severity: 'error' | 'warning'
    message: string
}
