/**
 * SVG helpers for node diagrams colors, legends, shadows, text escaping, sanitization.
 *
 * Both kubenode and datanode renderers pull from here to avoid duplication.
 * Got a new SVG renderer? Toss shared stuff in here.
 *
 * colors_for_status() status to color mapping
 * esc() escape entities for SVG text content
 * esc_attr() escape entities for SVG/XML attribute values
 * sanitize_svg() defense-in-depth DOMPurify pass for rendered SVG strings
 * render_legend() draw the connectivity legend at the bottom
 * render_shadow_filter() the drop-shadow filter <defs> block
 */

// External
import DOMPurify from 'dompurify'

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

// Colors for a port pill and its connected links
export interface PortColors {
    stroke: string
    text: string
    link: string
}

// Status to color mapping
export function colors_for_status(status: string | undefined): PortColors {
    if (status === 'open')     return { stroke: '#4ade80', text: '#166534', link: '#22c55e' }
    if (status === 'closed')   return { stroke: '#f87171', text: '#991b1b', link: '#ef4444' }
    if (status === 'filtered') return { stroke: '#fbbf24', text: '#92400e', link: '#f59e0b' }

    // No data / unknown neutral gray
    return { stroke: '#cbd5e1', text: '#64748b', link: '#94a3b8' }
}

// Escape entities so SVG doesn't choke on special chars
export function esc(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Escape a string for safe use inside an XML/SVG attribute value
export function esc_attr(value: string): string {
    return value
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
}

// ---------------------------------------------------------------------------
// SVG sanitization (defense-in-depth for any rendered SVG before DOM or canvas use)
// ---------------------------------------------------------------------------

/**
 * Defense-in-depth sanitization for rendered SVG strings.
 * The SVG renderers already escape dynamic values via esc()/esc_attr(),
 * but this DOMPurify pass catches anything a future renderer might miss.
 * Used by both the browser diagram composable and the PDF export path.
 *
 * @param raw_svg The raw SVG markup string from a renderer
 * @returns Sanitized SVG string safe for v-html or Image() loading
 */
export function sanitize_svg(raw_svg: string): string {
    return DOMPurify.sanitize(raw_svg, {
        USE_PROFILES: { svg: true, svgFilters: true },
    })
}

// ---------------------------------------------------------------------------
// Legend (appended to the bottom of each SVG)
// ---------------------------------------------------------------------------

export function render_legend(cx: number, y: number): string {
    let s = ''
    const items = [
        { color: '#4ade80', label: 'Open' },
        { color: '#f87171', label: 'Closed' },
        { color: '#fbbf24', label: 'Filtered' },
        { color: '#cbd5e1', label: 'Not tested' },
    ]
    let x = cx - 198
    s += `<text x="${x}" y="${y}" font-size="9" font-weight="600" fill="#64748b" letter-spacing="0.5">CONNECTIVITY:</text>`
    x += 95
    for (const item of items) {
        s += `<circle cx="${x}" cy="${y - 3}" r="5" fill="${item.color}"/>`
        s += `<text x="${x + 9}" y="${y}" font-size="9" fill="#64748b">${item.label}</text>`
        x += 75
    }
    return s
}

// ---------------------------------------------------------------------------
// Shadow filter <defs> block (shared by all node SVG renderers)
// ---------------------------------------------------------------------------

// Build the drop-shadow filter <defs> block
export function render_shadow_filter(fid: string): string {
    // Defense-in-depth: escape fid for attribute context even though current callers sanitize
    const safe_fid = esc_attr(fid)
    return `<defs>
    <filter id="${safe_fid}" x="-3%" y="-3%" width="106%" height="106%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="2" result="blur"/>
      <feOffset dx="1" dy="1" result="off"/>
      <feComponentTransfer in="off" result="fade"><feFuncA type="linear" slope="0.08"/></feComponentTransfer>
      <feMerge><feMergeNode in="fade"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>`
}
