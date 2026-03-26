/**
 * Gives checkers a fast way to look up data points and the gathering config.
 *
 * Data points are indexed by path for O(1) exact lookups and support regex
 * pattern matching for dynamic targets like vm/<node>/disk_usage.
 *
 * The gathering config (from the JSONL header) is available as data.config
 * so checkers can reference deployment-specific values like the cluster domain,
 * database IPs, and namespace instead of hardcoding or guessing.
 */

// Ours
import type { DataPoint, GatheringConfig } from '../sample-data'

/**
 * Safely parse a DataPoint's value as JSON and return a typed object.
 *
 * Returns null when the value is a boolean, null, not valid JSON, or
 * parses to a non-object primitive (number, string, null).
 * This prevents callers from accessing properties on a primitive, which
 * would silently return undefined instead of flagging a gather_failure.
 */
export function parse_json_value<T>(point: DataPoint): T | null {
    // Reject booleans and null — they aren't JSON objects
    if (typeof point.value === 'boolean' || point.value === null) {
        return null
    }

    try {
        const parsed = JSON.parse(String(point.value))

        // Reject primitives — checkers expect an object or array
        if (typeof parsed !== 'object' || parsed === null) {
            return null
        }

        return parsed as T
    } catch {
        return null
    }
}

/**
 * Coerce a value that may be a boolean or a string representation of a boolean
 * into an actual boolean.
 *
 * The Python gatherer sometimes serializes booleans as the strings "true" or
 * "false" instead of native JSON booleans. This helper normalises both forms
 * so checkers can safely compare with === without worrying about the type.
 *
 * Returns the original value unchanged when it is neither a boolean nor a
 * recognised boolean string, so callers can still detect unexpected types.
 */
export function coerce_boolean<T>(value: T): boolean | T {
    if (typeof value === 'boolean') return value
    if (typeof value === 'string') {
        const lower = value.toLowerCase()
        if (lower === 'true')  return true
        if (lower === 'false') return false
    }
    return value
}

/**
 * Safely coerce a DataPoint's value to a number at runtime.
 *
 * The Python gatherer may emit numeric values as strings (e.g. "92" or
 * "92%"). A TypeScript `as number` cast is compile-time only and does not
 * convert at runtime, so "92%" stays a string and comparisons like
 * `"92%" > 85` silently evaluate to false (NaN > 85 → false).
 *
 * This helper strips common suffixes (%, ms, s, MB, GB, etc.), attempts
 * numeric conversion, and returns null for anything unparseable so callers
 * can handle the failure explicitly.
 */
export function parse_number(point: DataPoint): number | null {
    const raw = point.value

    // Already a real number — pass through
    if (typeof raw === 'number') {
        return Number.isFinite(raw) ? raw : null
    }

    // Null / undefined / boolean / object — not a number
    if (raw === null || raw === undefined || typeof raw !== 'string') {
        return null
    }

    // Strip common unit suffixes and whitespace before parsing
    const cleaned = raw.trim().replace(/\s*(%|ms|s|mb|gb|tb|kb|mi|gi|ki)$/i, '').trim()

    if (cleaned === '') return null

    const num = Number(cleaned)
    return Number.isFinite(num) ? num : null
}

export class DataLookup {
    private points: Map<string, DataPoint>

    // The gathering config embedded in the JSONL file. Null when the JSONL
    // was produced by an older runner that didn't include the config header.
    readonly config: GatheringConfig | null

    // Tracks which DataPoints were accessed during the current checker run.
    // run_checks() uses this for metadata auto-attach instead of guessing
    // by path, which breaks when checker path != target path.
    // Keyed by path to prevent duplicates when find()/get() overlap.
    private _accessed: Map<string, DataPoint> = new Map()

    constructor(data_points: DataPoint[], config: GatheringConfig | null = null) {
        this.config = config
        this.points = new Map()
        for (const dp of data_points) {
            this.points.set(dp.path, dp)
        }
    }

    /** Reset access tracking between checker runs. */
    reset_accessed(): void {
        this._accessed = new Map()
    }

    /** DataPoints accessed since the last reset, in access order. */
    get accessed(): DataPoint[] {
        return Array.from(this._accessed.values())
    }

    /** Fetch a single data point by exact target path. */
    get(target_path: string): DataPoint | undefined {
        const point = this.points.get(target_path)

        // Track every access so run_checks() can find metadata for the details panel
        if (point) this._accessed.set(point.path, point)

        return point
    }

    /**
     * Fetch a data point by exact target path (alias for get).
     *
     * Historically, get() coerced null/undefined values to false, so get_raw()
     * existed to preserve the original value. That coercion has been removed;
     * both methods now behave identically. Kept for backwards compatibility.
     */
    get_raw(target_path: string): DataPoint | undefined {
        const point = this.points.get(target_path)

        // Track access for metadata auto-attach, same as get()
        if (point) this._accessed.set(point.path, point)

        return point
    }

    /**
     * Fetch a data point, skipping not_applicable sentinels.
     *
     * In kubernetes-only mode, SSH targets emit a sentinel data point with
     * metadata.not_applicable = true and value = null. A plain get() returns
     * this sentinel, which breaks «get(ssh_path) ?? get(direct_path)» because
     * the ?? sees a defined DataPoint and never falls through.
     *
     * Use this instead of get() when you have a fallback path so the sentinel
     * is transparently skipped.
     */
    get_applicable(target_path: string): DataPoint | undefined {
        const point = this.points.get(target_path)

        // Skip not_applicable sentinels so callers can fall through to alternatives
        if (point?.metadata?.not_applicable === true) return undefined

        // Track real (non-sentinel) accesses for metadata auto-attach
        if (point) this._accessed.set(point.path, point)

        return point
    }

    /**
     * Like get_applicable(), skips not_applicable sentinels (alias).
     *
     * Historically, get_applicable() coerced null/undefined to false, so this
     * raw variant preserved the original value. That coercion has been removed;
     * both methods now behave identically. Kept for backwards compatibility.
     */
    get_applicable_raw(target_path: string): DataPoint | undefined {
        const point = this.points.get(target_path)

        // Skip not_applicable sentinels, same as get_applicable()
        if (point?.metadata?.not_applicable === true) return undefined

        // Track real (non-sentinel) accesses for metadata auto-attach
        if (point) this._accessed.set(point.path, point)

        return point
    }

    /** Find all data points matching a regex pattern. */
    find(pattern: RegExp): DataPoint[] {
        // Strip global/sticky flags — RegExp.test() with /g or /y is stateful (lastIndex
        // advances after each match), causing unpredictable skipping when testing different strings.
        const safe = (pattern.global || pattern.sticky)
            ? new RegExp(pattern.source, pattern.flags.replace(/[gy]/g, ''))
            : pattern
        const matches: DataPoint[] = []
        for (const [path, dp] of this.points) {
            if (safe.test(path)) {
                matches.push(dp)
            }
        }

        // Track all matched points for metadata auto-attach
        for (const dp of matches) {
            this._accessed.set(dp.path, dp)
        }

        return matches
    }

    /**
     * Find all data points matching a regex, skipping not_applicable sentinels.
     *
     * Use this instead of find() when collecting per-host or per-service data
     * points — sentinels have value = null and would cause crashes or incorrect
     * aggregations if processed without checking.
     */
    find_applicable(pattern: RegExp): DataPoint[] {
        // Strip global/sticky flags for the same reason as find() — stateful lastIndex.
        const safe = (pattern.global || pattern.sticky)
            ? new RegExp(pattern.source, pattern.flags.replace(/[gy]/g, ''))
            : pattern
        const matches: DataPoint[] = []
        for (const [path, dp] of this.points) {
            if (safe.test(path) && dp.metadata?.not_applicable !== true) {
                matches.push(dp)
            }
        }

        // Track only real (non-sentinel) matches for metadata auto-attach
        for (const dp of matches) {
            this._accessed.set(dp.path, dp)
        }

        return matches
    }

    /** See if a target path was collected. */
    has(target_path: string): boolean {
        return this.points.has(target_path)
    }

    /**
     * Check if a data point was marked not-applicable.
     *
     * Returns true when the gatherer ran on the admin host and the target
     * needs external internet access, so the data point exists but got
     * intentionally skipped. Return { status: 'not_applicable' } instead
     * of trying to evaluate the (null) value.
     */
    is_not_applicable(target_path: string): boolean {
        const point = this.points.get(target_path)
        return point?.metadata?.not_applicable === true
    }

    /** Get all the data points we collected. */
    all(): DataPoint[] {
        return Array.from(this.points.values())
    }

    /**
     * Return the Kubernetes namespace from the gathering config.
     *
     * Falls back to 'wire' when the config is missing (older JSONL files
     * that don't include the config header).
     */
    get_kubernetes_namespace(): string {
        return this.config?.cluster.kubernetes_namespace ?? 'wire'
    }
}
