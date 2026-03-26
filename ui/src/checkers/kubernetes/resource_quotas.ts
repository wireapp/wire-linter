/**
 * Reports namespace resource quota usage.
 *
 * Without quotas, a runaway deployment can eat all cluster resources.
 * With quotas, operators need to watch usage approaching limits.
 *
 * Consumes: kubernetes/namespace/resource_quotas
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// Threshold for warning about quota usage (fraction)
const QUOTA_WARNING_THRESHOLD: number = 0.8

export class ResourceQuotasChecker extends BaseChecker {
    readonly path: string = 'kubernetes/resource_quotas'
    readonly name: string = 'Namespace resource quotas'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/namespace/resource_quotas'
    readonly explanation: string =
        '**ResourceQuotas** limit how much CPU, memory, and other resources a namespace can ' +
        'consume. Without them, a single runaway deployment can eat all cluster resources. ' +
        'When quotas exist, approaching limits means new deployments or scale-ups will be rejected.'

    check(data: DataLookup): CheckResult {
        const ns: string = data.get_kubernetes_namespace()
        const point = data.get('kubernetes/namespace/resource_quotas')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Resource quota data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            quota_count?: number
            quotas?: { name: string; hard: Record<string, string>; used: Record<string, string> }[]
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse quota data.' }
        }

        // Guard against null/primitive results (e.g. point.value was null → JSON.parse("null") → null)
        if (parsed === null || typeof parsed !== 'object') {
            return { status: 'gather_failure', status_reason: 'Quota data is not a valid object.' }
        }

        const quota_count: number = parsed.quota_count ?? 0

        // No quotas is informational, not necessarily a problem
        if (quota_count === 0) {
            return {
                status: 'healthy',
                status_reason: 'No resource quotas configured in the Wire namespace.',
                recommendation: 'Consider adding resource quotas to prevent resource exhaustion.',
                display_value: 'none',
                template_data: { near_count: 0 },
            }
        }

        // Check for resources approaching their limit
        const near_limit: string[] = []

        for (const quota of parsed.quotas ?? []) {
            for (const [resource, hard_str] of Object.entries(quota.hard)) {
                const used_str: string = quota.used[resource] ?? '0'
                const hard_val: number = _parse_resource_value(hard_str)
                const used_val: number = _parse_resource_value(used_str)

                if (hard_val > 0 && used_val / hard_val >= QUOTA_WARNING_THRESHOLD) {
                    const pct: number = Math.round((used_val / hard_val) * 100)
                    near_limit.push(`**${resource}**: ${used_str}/${hard_str} (${pct}%)`)
                }
            }
        }

        if (near_limit.length > 0) {
            return {
                status: 'warning',
                status_reason: `{{near_count}} resource(s) approaching quota limits (>80%).`,
                fix_hint: `Review quota usage:\n\`\`\`\nkubectl describe resourcequota -n ${ns}\n\`\`\`\nIncrease quotas or reduce resource requests to avoid deployment rejections.`,
                recommendation: `Resources near limit:\n- ${near_limit.join('\n- ')}`,
                display_value: `${near_limit.length} near limit`,
                template_data: { near_count: near_limit.length },
            }
        }

        return {
            status: 'healthy',
            status_reason: `${quota_count} resource quota(s) configured, all within limits.`,
            display_value: `${quota_count} quota(s)`,
            template_data: { near_count: 0 },
        }
    }
}

/**
 * Parse a Kubernetes resource value string to a number.
 * Handles all standard Kubernetes quantity suffixes:
 * - Binary (power-of-2): Ki, Mi, Gi, Ti, Pi, Ei
 * - Decimal (power-of-10): k, M, G, T, P, E
 * - Sub-unit: m (milli, 10^-3), u (micro, 10^-6), n (nano, 10^-9)
 *
 * Two-character suffixes are checked before one-character to avoid false matches.
 */
function _parse_resource_value(value: string): number {
    const trimmed: string = value.trim()

    // Extract numeric prefix and suffix via regex
    const match: RegExpMatchArray | null = trimmed.match(/^([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)(.*)$/)

    // No numeric prefix found — return 0 (e.g. bare 'm', 'Gi', or empty string)
    if (!match) return 0

    const num: number = parseFloat(match[1] ?? '0')
    const suffix: string = match[2] ?? ''

    // No suffix — plain number
    if (suffix === '') return num

    // Binary suffixes (2-char, checked first)
    if (suffix === 'Ei') return num * (2 ** 60)
    if (suffix === 'Pi') return num * (2 ** 50)
    if (suffix === 'Ti') return num * (2 ** 40)
    if (suffix === 'Gi') return num * (2 ** 30)
    if (suffix === 'Mi') return num * (2 ** 20)
    if (suffix === 'Ki') return num * (2 ** 10)

    // Decimal suffixes (1-char)
    if (suffix === 'E') return num * 1e18
    if (suffix === 'P') return num * 1e15
    if (suffix === 'T') return num * 1e12
    if (suffix === 'G') return num * 1e9
    if (suffix === 'M') return num * 1e6
    if (suffix === 'k') return num * 1e3

    // Sub-unit suffixes
    if (suffix === 'n') return num * 1e-9
    if (suffix === 'u') return num * 1e-6
    if (suffix === 'm') return num * 1e-3

    // Unrecognized suffix — return the numeric portion
    return num
}

export default ResourceQuotasChecker
