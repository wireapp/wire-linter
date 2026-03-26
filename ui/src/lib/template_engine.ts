// Template engine: Handlebars compilation with LRU-cached template rendering
// for checker explanation, status_reason, and fix_hint templates.
//
// Public API:
//   render_template(template, context)   compile Handlebars template and render with context
//
// Templates are Markdown strings with Handlebars expressions. The engine
// compiles and renders them, producing Markdown ready for the markdown renderer.
//
// Brace convention (enforced):
//   {{var}}   — plain values: numbers, short strings without Markdown formatting
//              Handlebars HTML-escapes these (&, <, > → entities), providing
//              defense-in-depth even though template data comes from checker code.
//   {{{var}}} — Markdown content: values containing bold (**x**), code (`x`), or newlines
//              Passed through raw (no HTML escaping); the Markdown renderer / DOMPurify
//              downstream handles sanitization.

// External
import Handlebars from 'handlebars'

// ── Template cache ───────────────────────────────────────────────────────────

// Maximum number of compiled templates to cache before evicting the least recently used.
// 500 is well above the ~300 templates used by checkers, leaving headroom without unbounded growth.
const MAX_CACHE_SIZE = 500

// LRU cache: Map iteration order reflects insertion order. On cache hit we
// delete-then-reinsert to move the entry to the "most recent" end. When the
// map exceeds MAX_CACHE_SIZE, we evict the first (oldest) entry.
const template_cache = new Map<string, HandlebarsTemplateDelegate>()

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * Compile a Handlebars template string and render it with the given context.
 * Returns the rendered Markdown string. If the template contains no Handlebars
 * expressions, it passes through unchanged (fast path).
 *
 * @param template  Handlebars + Markdown template string
 * @param context   Key-value pairs for template variable substitution
 * @returns         Rendered Markdown string
 */
export function render_template(template: string, context: Record<string, unknown> = {}): string {
    if (!template) return ''

    // Fast path: no Handlebars expressions, return as-is
    if (!template.includes('{{')) return template

    try {
        let compiled = template_cache.get(template)
        if (compiled) {
            // Move to most-recently-used position by reinserting at the end
            template_cache.delete(template)
            template_cache.set(template, compiled)
        } else {
            // Standard Handlebars escaping: {{var}} HTML-escapes special chars (&, <, >, "),
            // while {{{var}}} passes values through raw. Template data values that contain
            // Markdown formatting must use {{{var}}} — plain values (numbers, names) use {{var}}.
            compiled = Handlebars.compile(template)
            template_cache.set(template, compiled)

            // Evict least recently used entry if cache exceeds max size
            if (template_cache.size > MAX_CACHE_SIZE) {
                const oldest_key = template_cache.keys().next().value as string
                template_cache.delete(oldest_key)
            }
        }

        return compiled(context)
    } catch (error) {
        // Template has syntax errors or a helper threw — return raw template
        // so the report still renders instead of crashing entirely
        const detail = error instanceof Error ? error.message : String(error)
        console.warn(`Template render failed: ${detail}`)
        return template
    }
}
