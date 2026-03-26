/**
 * Checks if your disk space triggered the flood-stage watermark in Elasticsearch.
 * When that happens, Elasticsearch silently locks all indices as read-only,
 * which breaks search indexing. New messages don't appear in search results
 * and nobody knows why-that's why this check matters.
 * The target returns a boolean where true = healthy (not read-only), false = bad (watermark triggered).
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

/**
 * Recursively searches a parsed JSON object for read_only_allow_delete set to "true" or true.
 * This is the specific Elasticsearch cluster setting that indicates flood-stage watermark was triggered.
 */
function has_read_only_flag(obj: unknown): boolean {
    if (typeof obj !== 'object' || obj === null) return false

    const record = obj as Record<string, unknown>

    // Direct property check for the specific Elasticsearch setting
    if ('read_only_allow_delete' in record) {
        const flag: unknown = record['read_only_allow_delete']
        if (flag === true || flag === 'true') return true
    }

    // Recurse into nested objects (ES settings are deeply nested)
    for (const value of Object.values(record)) {
        if (typeof value === 'object' && value !== null && has_read_only_flag(value)) {
            return true
        }
    }

    return false
}

export class ReadOnlyModeChecker extends BaseChecker {
    readonly path: string = 'elasticsearch/read_only_mode'
    readonly data_path: string = 'databases/elasticsearch/read_only_check'
    readonly name: string = 'Read-only mode / disk watermark'
    readonly category: string = 'Data / Elasticsearch'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Detects whether Elasticsearch has entered **read-only mode** due to the disk flood-stage watermark being triggered. When this happens, all indices are silently locked and new Wire messages stop appearing in search results.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/elasticsearch/read_only_check')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch read-only mode / disk watermark data was not collected.',
                fix_hint: '1. Verify connectivity to the Elasticsearch cluster\n2. Check the index settings API: `curl -s http://localhost:9200/_all/_settings?pretty | grep read_only`\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Read-only mode / disk watermark data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Elasticsearch read-only mode data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Read-only mode target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // When it's true, we're not in read-only mode-that's good
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Elasticsearch is **not** in read-only mode; disk watermark has not been triggered.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // When it's false, read-only mode is active-disk watermark hit
        if (val === false) {
            return {
                status: 'unhealthy',
                status_reason: 'Elasticsearch is in **read-only mode** because the disk flood-stage watermark was triggered.',
                fix_hint: '1. Check disk usage on data nodes: `curl -s http://localhost:9200/_cat/allocation?v`\n2. Free disk space by removing old indices or data\n3. After freeing space, remove the read-only block: `curl -s -X PUT http://localhost:9200/_all/_settings -H "Content-Type: application/json" -d \'{"index.blocks.read_only_allow_delete": null}\'`\n4. Verify indices are writable: `curl -s http://localhost:9200/_all/_settings?pretty | grep read_only`\n5. Adjust watermark thresholds if needed: `curl -s -X PUT http://localhost:9200/_cluster/settings -H "Content-Type: application/json" -d \'{"persistent": {"cluster.routing.allocation.disk.watermark.flood_stage": "95%"}}\'`',
                recommendation: 'Elasticsearch is in read-only mode (disk watermark triggered). Search and indexing have silently stopped. Free disk space on data nodes.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // If it's a string, try to parse as JSON first, then fall back to substring checks
        if (typeof val === 'string') {
            // Attempt JSON parse to check the specific read_only_allow_delete property
            try {
                const parsed: unknown = JSON.parse(val)
                if (typeof parsed === 'object' && parsed !== null) {
                    const is_read_only: boolean = has_read_only_flag(parsed)
                    if (is_read_only) {
                        return {
                            status: 'unhealthy',
                            status_reason: `Elasticsearch response indicates read-only mode is active: «${val}».`,
                            recommendation: 'Elasticsearch is in read-only mode (disk watermark triggered). Search and indexing have silently stopped. Free disk space on data nodes.',
                            display_value: val,
                            raw_output: point.raw_output,
                        }
                    }
                    return {
                        status: 'healthy',
                        status_reason: 'Elasticsearch response contains no read-only indicators; indices are writable.',
                        display_value: val,
                        raw_output: point.raw_output,
                    }
                }
            } catch {
                // Not valid JSON, fall through to substring checks
            }

            // Fallback: substring check for non-JSON strings, but only match read_only keywords
            const lower: string = val.toLowerCase()
            if (lower.includes('read_only')) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Elasticsearch response indicates **read-only mode** is active: **{{es_response}}**.',
                    fix_hint: '1. Check disk usage on data nodes: `curl -s http://localhost:9200/_cat/allocation?v`\n2. Free disk space by removing old indices or data\n3. After freeing space, remove the read-only block: `curl -s -X PUT http://localhost:9200/_all/_settings -H "Content-Type: application/json" -d \'{"index.blocks.read_only_allow_delete": null}\'`\n4. Verify indices are writable: `curl -s http://localhost:9200/_all/_settings?pretty | grep read_only`',
                    recommendation: 'Elasticsearch is in read-only mode (disk watermark triggered). Search and indexing have silently stopped. Free disk space on data nodes.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { es_response: val },
                }
            }

            // String with no read-only indicators is fine
            return {
                status: 'healthy',
                status_reason: 'Elasticsearch response contains no read-only indicators; indices are writable.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Numbers or other types-assume it's okay
        return {
            status: 'healthy',
            status_reason: 'Elasticsearch read-only check returned a non-boolean/non-string value; assuming indices are writable.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default ReadOnlyModeChecker
