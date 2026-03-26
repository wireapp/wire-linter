/**
 * Shared helper utilities for HTTP response string interpretation.
 *
 * Provides keyword detection helpers used by checkers that receive
 * HTTP probe results as strings (e.g. webapp_http, ingress_response).
 * Centralising these checks keeps the keyword lists in sync across all
 * checkers and prevents future drift.
 *
 * Functions:
 *   is_http_success_keyword  - detects known "all-good" string responses
 *   is_http_error_keyword    - detects known network / connection error strings
 */

/**
 * Returns true when the string value is a recognised success keyword.
 *
 * Collectors that cannot return a numeric HTTP code sometimes return a
 * plain-text status word.  This covers the common cases so checkers can
 * produce an accurate "healthy" result instead of falling through to an
 * "unexpected response" error.
 *
 * @param value - The raw string value from the data point.
 * @returns True if the value matches a known success keyword.
 */
export function is_http_success_keyword(value: string): boolean {
    const lower: string = value.toLowerCase().trim()
    return lower === 'ok' || lower === 'success' || lower === 'healthy'
}

/**
 * Returns true when the string value contains a recognised network error keyword.
 *
 * These keywords appear in error messages produced by curl, wget, and
 * similar tools when a connection fails at the network layer rather than
 * returning an HTTP status code.  Detecting them lets checkers surface a
 * specific "could not be reached: connection refused" message instead of the
 * generic "unexpected response" fallback.
 *
 * @param value - The raw string value from the data point.
 * @returns True if the value contains a known network error keyword.
 */
export function is_http_error_keyword(value: string): boolean {
    const lower: string = value.toLowerCase().trim()
    return lower.includes('timeout')
        || lower.includes('connection refused')
        || lower.includes('connection reset')
        || lower.includes('unreachable')
        || lower.includes('no route')
        || lower.includes('dns resolution failed')
        || lower.includes('could not resolve host')
        || lower.includes('name or service not known')
        || lower.includes('failed to connect')
}
