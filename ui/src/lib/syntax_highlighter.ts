// Syntax highlighting pure string to string transforms for rendering
// JSON, YAML, and plain text as coloured HTML in «pre v-html» blocks.
//
// Public API:
//   highlight_content(content)          auto-detect format and highlight
//   extract_yaml_entries_from_json(raw) pull embedded YAML blobs from JSON
//
// Internal helpers: escape_html, hl, detect_format, colorize_yaml_value,
// highlight_yaml_line, highlight_json.
//
// Needs js-yaml to extract YAML entries from JSON.

// External
import DOMPurify from 'dompurify'
import yaml from 'js-yaml'

// ---------------------------------------------------------------------------
// YAML extraction
// ---------------------------------------------------------------------------

// Extract YAML config blobs embedded as string values in a JSON object.
// Parses raw_output as JSON, walks the whole tree looking for string values
// that parse as YAML mappings, returns {key, content} pairs so the ConfigMap
// button works for any check with embedded YAML config.
export function extract_yaml_entries_from_json(raw_output: string): Array<{key: string, content: string}> {
    if (!raw_output) return []

    let parsed: unknown
    try {
        parsed = JSON.parse(raw_output)
    } catch {
        // Not valid JSON skip it
        return []
    }

    if (typeof parsed !== 'object' || parsed === null) return []

    const entries: Array<{key: string, content: string}> = []

    // Recursively walk the JSON tree looking for string values that parse as YAML mappings
    function scan(obj: unknown, path: string): void {
        if (typeof obj === 'string') {
            // Skip strings that don't look like YAML (no newlines or doc markers)
            if (!obj.includes('\n') && !obj.trimStart().startsWith('---')) return
            try {
                const yaml_parsed = yaml.load(obj)
                // Only accept objects scalars like «hello» parse as YAML too but we don't want 'em
                if (yaml_parsed !== null && typeof yaml_parsed === 'object' && !Array.isArray(yaml_parsed)) {
                    entries.push({ key: path, content: obj })
                }
            } catch {
                // Most strings aren't YAML no big deal
            }
        } else if (Array.isArray(obj)) {
            obj.forEach((item, idx) => scan(item, `${path}[${idx}]`))
        } else if (typeof obj === 'object' && obj !== null) {
            for (const [k, v] of Object.entries(obj)) {
                scan(v, path ? `${path}.${k}` : k)
            }
        }
    }

    scan(parsed, '')
    return entries
}

// ---------------------------------------------------------------------------
// Low-level helpers
// ---------------------------------------------------------------------------

// Keep XSS out of v-html blocks escape HTML special chars including single quotes
export function escape_html(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;')
}

// All valid highlight class names used in syntax colouring
type HlClass = 'hl-comment' | 'hl-keyword' | 'hl-string' | 'hl-meta' | 'hl-number' | 'hl-doc-marker' | 'hl-punctuation' | 'hl-key'

// Wrap text in a styled span for syntax highlighting
// Escapes text internally so callers never need to pre-escape
export function hl(cls: HlClass, text: string): string {
    return `<span class="${cls}">${escape_html(text)}</span>`
}

// ---------------------------------------------------------------------------
// Format detection
// ---------------------------------------------------------------------------

// Figure out if content is JSON, YAML, or just plain text
export function detect_format(content: string): 'json' | 'yaml' | 'text' {
    const trimmed = content.trim()

    // JSON starts with { or [ and has to parse
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
            JSON.parse(trimmed)
            return 'json'
        } catch {
            // Nope check if it's YAML instead
        }
    }

    // YAML: document marker, or lines with key: value patterns
    if (trimmed.startsWith('---') || /^[\w.-]+\s*:/m.test(trimmed)) {
        return 'yaml'
    }

    return 'text'
}

// ---------------------------------------------------------------------------
// YAML highlighting
// ---------------------------------------------------------------------------

// Colorize the value part of a YAML line (after the colon, or a list value)
export function colorize_yaml_value(raw: string): string {
    const trimmed = raw.trim()

    if (!trimmed) return escape_html(raw)

    // Value is entirely a comment (empty value followed by comment)
    if (/^\s*#/.test(raw)) return hl('hl-comment', raw)

    // Inline comment split: match " #" preceded by non-# content
    // Skip for quoted strings — a # inside quotes is not a comment
    const is_quoted = /^\s*["']/.test(raw)
    if (!is_quoted) {
        const comment_idx = raw.search(/\s+#/)
        if (comment_idx > 0) {
            const before  = raw.slice(0, comment_idx)
            const comment = raw.slice(comment_idx)
            return colorize_yaml_value(before) + hl('hl-comment', comment)
        }
    }

    // Block scalar indicator: | or >
    if (/^\s*[|>][-+]?\s*$/.test(raw)) return hl('hl-keyword', raw)

    // Quoted strings (single or double)
    if (/^\s*["']/.test(raw)) return hl('hl-string', raw)

    // Anchors (&name) and aliases (*name)
    if (/^\s*[&*]/.test(raw)) return hl('hl-meta', raw)

    // Numbers (integer, float, scientific)
    if (/^\s*-?\d+(\.\d+)?([eE][+-]?\d+)?\s*$/.test(raw)) return hl('hl-number', raw)

    // Booleans and null variants used in YAML
    if (/^\s*(true|false|yes|no|null|~)\s*$/i.test(raw)) return hl('hl-keyword', raw)

    // Plain string value
    return hl('hl-string', raw)
}

// Highlight a single YAML line and spit out HTML
export function highlight_yaml_line(line: string): string {
    // Full-line comment
    if (/^\s*#/.test(line)) return hl('hl-comment', line)

    // YAML document/directive markers
    if (/^\s*(---|\.\.\.)\s*$/.test(line)) return hl('hl-doc-marker', line)

    // Key: value line optionally preceded by list dash
    // Matches: (indent)(optional "- ")(key)(: )(rest)
    const key_match = /^(\s*)(- )?([\w.-]+)(\s*:)(.*)?$/.exec(line)
    if (key_match) {
        // Groups 1, 3, 4 always capture when the regex matches; group 2 is optional (dash)
        const [, indent, dash, key, colon, rest] = key_match
        return (
            escape_html(indent!) +
            (dash ? hl('hl-punctuation', dash) : '') +
            hl('hl-key', key!) +
            hl('hl-punctuation', colon!) +
            colorize_yaml_value(rest ?? '')
        )
    }

    // Bare list item (- value, no key)
    const list_match = /^(\s*- )(.*)$/.exec(line)
    if (list_match) {
        // Both groups always capture when the regex matches
        const [, dash, value] = list_match
        return hl('hl-punctuation', dash!) + colorize_yaml_value(value!)
    }

    return escape_html(line)
}

// ---------------------------------------------------------------------------
// JSON highlighting
// ---------------------------------------------------------------------------

// Highlight JSON and return HTML pretty-prints if it parses
export function highlight_json(content: string): string {
    let formatted = content
    try {
        formatted = JSON.stringify(JSON.parse(content), null, 2)
    } catch {
        // Just use it as-is if it doesn't parse
    }

    // Token-by-token pass color strings, numbers, booleans, punctuation.
    // List \n before . cause . doesn't match newlines in JS.
    const token_re = /"(?:[^"\\]|\\.)*"(?:\s*:)?|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}[\],:]|\n|./g
    let result = ''
    let match: RegExpExecArray | null

    while ((match = token_re.exec(formatted)) !== null) {
        const token = match[0]

        if (token === '\n') { result += '\n'; continue }

        if (/^"/.test(token)) {
            // Key (ends with optional whitespace + colon) vs string value
            const key_match = token.match(/^("(?:[^"\\]|\\.)*")(\s*:)$/)
            if (key_match) {
                result += hl('hl-key', key_match[1]!) + hl('hl-punctuation', key_match[2]!)
            } else {
                result += hl('hl-string', token)
            }
        } else if (token === 'true' || token === 'false' || token === 'null') {
            result += hl('hl-keyword', token)
        } else if (/^-?\d/.test(token)) {
            result += hl('hl-number', token)
        } else if ('{[}],:'.includes(token)) {
            result += hl('hl-punctuation', token)
        } else {
            // Fallback for whitespace and unrecognized tokens
            result += escape_html(token)
        }
    }

    return result
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

// Auto-detect and return syntax-highlighted HTML for v-html rendering.
// Output is sanitised with DOMPurify as defense-in-depth because raw_output
// originates from external command execution on remote servers.
export function highlight_content(content: string): string {
    if (!content) return ''

    const format = detect_format(content)

    let html: string
    if (format === 'json') html = highlight_json(content)
    else if (format === 'yaml') html = content.split('\n').map(highlight_yaml_line).join('\n')
    else html = escape_html(content)

    // Allow only the span+class markup produced by hl() — strip anything else
    return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['span'], ALLOWED_ATTR: ['class'] })
}
