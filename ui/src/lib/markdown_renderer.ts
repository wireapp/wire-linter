// Markdown renderer: converts Markdown strings to sanitised HTML for v-html rendering.
//
// Public API:
//   render_markdown(md)   convert Markdown to HTML string
//
// Uses the `marked` library configured for inline rendering (paragraphs produce
// <span> not <p> for short single-line texts) with code highlighting classes
// that match the existing terminal/code styling in the app.

// External
import DOMPurify from 'dompurify'
import { Marked } from 'marked'

// ── Configuration ────────────────────────────────────────────────────────────

// Isolated instance avoids mutating the global marked singleton, so other
// consumers of the library keep their own default options.
const md = new Marked({
    // GFM for tables, strikethrough, task lists
    gfm: true,
    // Line breaks within paragraphs become <br>
    breaks: true,
})

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * Render a Markdown string to HTML. Returns sanitised HTML safe for v-html.
 * Short single-line strings without block elements are returned without
 * wrapping <p> tags for cleaner inline display.
 *
 * @param markdown  Markdown source string
 * @returns   HTML string ready for v-html
 */
export function render_markdown(markdown: string): string {
    if (!markdown) return ''

    const raw_html = md.parse(markdown, { async: false }) as string

    // Sanitize first, allowing <command> through so it survives intact.
    // We convert <command> → <code> *after* sanitization so any malicious
    // content inside <command> tags gets neutralised before it lands in <code>.
    const html = DOMPurify.sanitize(raw_html, {
        ADD_TAGS: ['command'],
    })

    // Now safely convert the sanitised <command> elements to <code>
    const converted = html.replace(/<command>([\s\S]*?)<\/command>/g, '<code>$1</code>')

    // Second sanitization pass (without ADD_TAGS) strips any <command> tags
    // that survived the regex, e.g. from nested or malformed pairs.
    const sanitised = DOMPurify.sanitize(converted)

    // Strip wrapping <p>...</p> for single-paragraph content so it renders
    // inline without extra vertical spacing in compact UI sections
    const trimmed = sanitised.trim()
    // Regex handles <p> with or without attributes (e.g. <p dir="auto">)
    const single_p = /^<p(\s[^>]*)?>([^]*)<\/p>$/
    const m = single_p.exec(trimmed)
    const inner = m?.[2]
    if (inner !== undefined && !inner.includes('<p')) return inner

    return trimmed
}
