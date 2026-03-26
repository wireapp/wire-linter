// Display and formatting utilities: pure string-to-string transforms used to render
// checker results, data points, and recommendations in the UI.
//
// Public API:
//   format_value(value, unit?)           format a check/data value for display
//   status_icon(status)                  PrimeIcons class for a check status
//   status_label(status)                 human-readable badge label for a status
//   format_timestamp(iso)                UTC-normalised YYYY-MM-DD HH:mm:ss from ISO 8601
//
// Pulled out of App.vue so we can reuse these across components (CheckResultsTree,
// DataPointsTree, report_pdf, etc.) without duplicating code.


// Value formatting

/**
 * Format a check or data-point value for display. Returns a dash for
 * missing values, «Yes»/«No» for booleans, and adds the unit if provided.
 */
export function format_value(value: string | number | boolean | null | undefined, unit?: string): string {
    if (value === undefined || value === null) return '\u2014'
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    if (unit) return `${value} ${unit}`
    return String(value)
}

// Status helpers

/**
 * Get the PrimeIcons CSS class for a check status.
 */
export function status_icon(status: string): string {
    if (status === 'healthy')         return 'pi pi-check-circle'
    if (status === 'warning')         return 'pi pi-exclamation-triangle'
    if (status === 'gather_failure')  return 'pi pi-exclamation-triangle'
    if (status === 'not_applicable')  return 'pi pi-minus-circle'
    return 'pi pi-times-circle'
}

/**
 * Convert snake_case status values to human-readable badge labels
 * (e.g. «not_applicable» becomes «N/A»).
 */
export function status_label(status: string): string {
    if (status === 'not_applicable') return 'N/A'
    if (status === 'gather_failure') return 'gather failure'
    return status
}

// Duration formatting

/**
 * Safely format a duration value for display. Handles strings, numbers, null,
 * and undefined — the JSONL data comes from Python via JSON.parse so the
 * runtime type may not match the TypeScript interface.
 */
export function format_duration(val: unknown, decimals: number): string {
    if (val === undefined || val === null) return ''
    const num = Number(val)
    if (isNaN(num)) return String(val)
    return num.toFixed(decimals)
}

// Timestamp formatting

/**
 * Format an ISO 8601 timestamp as YYYY-MM-DD HH:mm:ss in UTC. Uses UTC
 * getters so the time stays consistent regardless of the operator's timezone.
 * A UTC+1 machine would otherwise show a 23:00Z timestamp as 00:00 the next day.
 * Returns empty string for missing input, and the raw string if parsing fails.
 */
export function format_timestamp(iso: string | undefined): string {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const year    = d.getUTCFullYear()
    const month   = String(d.getUTCMonth() + 1).padStart(2, '0')
    const day     = String(d.getUTCDate()).padStart(2, '0')
    const hours   = String(d.getUTCHours()).padStart(2, '0')
    const minutes = String(d.getUTCMinutes()).padStart(2, '0')
    const seconds = String(d.getUTCSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}
