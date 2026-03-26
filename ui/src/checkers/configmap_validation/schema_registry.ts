/**
 * Version-aware schema registry for ConfigMap validation.
 *
 * Loads all JSON schemas from versioned folders at build time using Vite's
 * import.meta.glob, then hands out the right schema for whatever wire-server
 * version you're running. Instead of hardcoding one schema, we validate against
 * the version that actually matches your deployment.
 *
 * Schemas live in: assets/schemas/<version>/<service>.schema.json
 * Like this: assets/schemas/5.22.0/brig.schema.json
 *
 * Main functions:
 * get_versioned_schema: finds the highest schema version <= what you've got
 * detect_wire_server_version: pulls the version out of helm/release_status
 * get_known_versions: lists all available schema versions in order
 */

// Ours
import type { DataLookup } from '../data_lookup'

/**
 * Semver split into numbers so we can compare versions.
 */
interface SemVer {
    major: number
    minor: number
    patch: number
    raw: string
}

/**
 * Map of version -> service -> schema. Built once when the module loads.
 */
const schema_map: Map<string, Map<string, Record<string, unknown>>> = new Map()

/**
 * All known schema versions, sorted low to high. We cache this
 * so we don't have to re-sort on every lookup.
 */
let sorted_versions: SemVer[] = []

// Load every JSON schema from versioned subfolders at build time.
// Vite figures this out, each file lands in the bundle.
const raw_schemas: Record<string, Record<string, unknown>> = import.meta.glob(
    '../../assets/schemas/*/*.schema.json',
    { eager: true, import: 'default' },
)

/**
 * Turn a «X.Y.Z» string into a SemVer so we can compare versions numerically.
 *
 * @param version_string Like «5.22.0»
 * @returns SemVer object with the parts broken out, or null if it's garbage
 */
function parse_semver(version_string: string): SemVer | null {
    // Split on dots, need exactly three parts
    const parts = version_string.split('.')

    if (parts.length !== 3) return null

    const major = Number(parts[0])
    const minor = Number(parts[1])
    const patch = Number(parts[2])

    // If any part isn't a number, bail out
    if (Number.isNaN(major) || Number.isNaN(minor) || Number.isNaN(patch)) return null

    return { major, minor, patch, raw: version_string }
}

/**
 * Compare two SemVer objects. Negative if a < b, zero if they're the same,
 * positive if a > b. Works with Array.sort().
 *
 * @param a First version
 * @param b Second version
 * @returns Number you can use for sorting
 */
function compare_semver(a: SemVer, b: SemVer): number {
    // Major comes first
    if (a.major !== b.major) return a.major - b.major

    // Then minor
    if (a.minor !== b.minor) return a.minor - b.minor

    // Finally patch
    return a.patch - b.patch
}

/**
 * Build the schema_map and sorted_versions from the glob results.
 * Runs once when the module loads.
 */
function build_registry(): void {
    // Glob paths look like: ../../assets/schemas/<version>/<service>.schema.json
    // They're relative to where this file sits.
    const path_regex = /\/schemas\/([^/]+)\/([^/]+)\.schema\.json$/

    for (const [file_path, schema] of Object.entries(raw_schemas)) {
        const match = path_regex.exec(file_path)
        if (!match) continue

        const version_string = match[1]
        const service_name   = match[2]

        // Regex guarantees these but we guard anyway
        if (version_string === undefined || service_name === undefined) continue

        // Create the version bucket if needed
        if (!schema_map.has(version_string)) {
            schema_map.set(version_string, new Map())
        }

        // Store the schema under its service name (like «brig» or «background-worker»)
        schema_map.get(version_string)!.set(service_name, schema as Record<string, unknown>)
    }

    // Build the sorted version list for fast lookups
    const parsed: SemVer[] = []
    for (const version_string of schema_map.keys()) {
        const sv = parse_semver(version_string)
        if (sv) parsed.push(sv)
    }

    // Sort ascending so finding the highest version <= target is quick
    parsed.sort(compare_semver)
    sorted_versions = parsed
}

// Build the registry when we load
build_registry()

/**
 * Get the schema for a service at a specific wire-server version.
 * Finds the highest schema version we've got that's <= your detected version.
 * Returns null if nothing matches.
 *
 * @param wire_server_version Like «5.23.0»
 * @param service_name Like «brig» or «background-worker»
 * @returns The schema and which version it came from, or null
 */
export function get_versioned_schema(
    wire_server_version: string,
    service_name: string,
): { schema: Record<string, unknown>; schema_version: string } | null {
    const target = parse_semver(wire_server_version)

    // Can't parse it, can't match anything
    if (!target) return null

    // Walk backwards through sorted versions to find the highest one that's <= target
    let best_match: SemVer | null = null
    for (let index = sorted_versions.length - 1; index >= 0; index--) {
        const candidate = sorted_versions[index]
        if (candidate !== undefined && compare_semver(candidate, target) <= 0) {
            best_match = candidate
            break
        }
    }

    // Didn't find any schema version that's <= what you've got
    if (!best_match) return null

    // Grab the schemas for that version
    const version_schemas = schema_map.get(best_match.raw)
    if (!version_schemas) return null

    const schema = version_schemas.get(service_name)
    if (!schema) return null

    return { schema, schema_version: best_match.raw }
}

/**
 * Pull the wire-server chart version out of the data we collected.
 *
 * Tries three sources in order:
 * 1. helm/release_status raw output (from «helm list -A»)
 * 2. helm/releases raw output or value field
 * 3. Brig container image tag from wire_services/brig/healthy (kubectl fallback)
 *
 * The third fallback enables version detection in k8s-only mode where
 * helm CLI data isn't available but brig pod JSON is.
 *
 * @param data DataLookup instance with helm and/or service data
 * @returns Version string like «5.23.0», or null
 */
export function detect_wire_server_version(data: DataLookup): string | null {
    // helm/release_status has the output of `helm list -A` with chart versions in it
    const release_status = data.get_applicable('helm/release_status') ?? data.get('direct/helm/release_status')

    if (release_status?.raw_output) {
        // Look for «wire-server-X.Y.Z» in there
        const chart_match = /wire-server-(\d+\.\d+\.\d+)/.exec(release_status.raw_output)
        if (chart_match) return chart_match[1]!
    }

    // Try helm/releases in case the data format's different
    const releases = data.get_applicable('helm/releases') ?? data.get('direct/helm/releases')

    if (releases?.raw_output) {
        const fallback_match = /wire-server-(\d+\.\d+\.\d+)/.exec(releases.raw_output)
        if (fallback_match) return fallback_match[1]!
    }

    // Last attempt: check the value field
    if (releases) {
        const value_string = String(releases.value)
        const value_match  = /wire-server-(\d+\.\d+\.\d+)/.exec(value_string)
        if (value_match) return value_match[1]!
    }

    // Fallback for k8s-only mode: extract version from brig container image tag.
    // The brig health target collects full pod JSON via kubectl, which includes
    // container images like «quay.io/wire/brig:5.23.0». The image tag matches
    // the wire-server chart version because Wire publishes all service images
    // with the chart version as the tag.
    const brig_health = data.get('wire_services/brig/healthy')

    if (brig_health?.raw_output) {
        const image_match = /quay\.io\/wire\/brig:(\d+\.\d+\.\d+)/.exec(brig_health.raw_output)
        if (image_match) return image_match[1]!
    }

    return null
}

/**
 * List all the schema versions we know about, sorted low to high.
 *
 * @returns Array of version strings like [«5.22.0», «5.22.52», «5.23.0»]
 */
export function get_known_versions(): string[] {
    return sorted_versions.map((sv) => sv.raw)
}
