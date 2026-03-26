/**
 * Professional multi-chapter PDF report generator for Wire deployment health results.
 *
 * Produces a polished, full-featured A4 PDF with four chapters:
 *   Chapter 1 Health Check Results (status-sorted, grouped by category)
 *   Chapter 2 Data Points (path-hierarchy grouped, all collected values)
 *   Chapter 3 Port Connectivity (table of all probed connections)
 *   Chapter 4 Network Diagrams (per-node SVG diagrams rendered via canvas)
 *
 * Entry point:
 *   download_report(results, data_points) -> triggers browser download
 *
 * Layout helpers (private):
 *   new_page(), ensure_space(), draw_chapter_heading(),
 *   draw_badge(), draw_summary_cards(), draw_toc(), add_footers()
 *
 * SVG rendering:
 *   svg_to_png_data_url() async, uses browser canvas to rasterise SVGs
 *   build_diagram_svgs() collects unique nodes and renders their SVGs
 *   extract_port_results() parses PORT_RESULTS_JSON lines from raw_output
 *
 * Concurrency safety:
 *   All mutable rendering state (doc, y) lives in a RenderCtx object created
 *   fresh inside download_report and threaded through every helper. There are
 *   no module-level mutable variables, so concurrent calls cannot interfere.
 */

// External
import { jsPDF } from 'jspdf'
import { Marked } from 'marked'

// Ours
import type { CheckOutput } from '../checkers/base_checker'
import type { DataPoint } from '../sample-data'
import { format_value, format_timestamp } from './format_utils'
import { worst_status_per_port, infer_node_type } from '../composables/use_port_diagrams'
import type { PortCheckResult } from './port_types'
import { render_kubenode_svg } from './kubenode_svg'
import { render_datanode_svg } from './datanode_svg'
import { render_external_svg } from './external_svg'
import { sanitize_svg } from './svg_helpers'

// Constants

// A4 dimensions in mm (jsPDF default unit)
const PAGE_W  = 210
const PAGE_H  = 297
const MARGIN  = 15   // left and right margin in mm
const MARGIN_T = 18  // top margin
const MARGIN_B = 20  // bottom margin (footer area)

// Printable width = total width minus both margins
const CONTENT_W = PAGE_W - MARGIN * 2

// Bottom threshold: add new page if y exceeds this
const Y_MAX = PAGE_H - MARGIN_B

// Wire brand and status palette (RGB triples)
const C_BLUE    = [6,   103, 200] as const
const C_GREEN   = [21,  128, 61]  as const
const C_AMBER   = [180, 83,  9]   as const
const C_RED     = [185, 28,  28]  as const
const C_DARK    = [31,  41,  55]  as const
const C_GRAY    = [107, 114, 128] as const
const C_WHITE   = [255, 255, 255] as const

// Light background fills for status badge pills
const CB_GREEN  = [220, 252, 231] as const
const CB_AMBER  = [254, 243, 199] as const
const CB_RED    = [254, 226, 226] as const
const CB_GRAY   = [243, 244, 246] as const
const CB_BLUE   = [219, 234, 254] as const

// Very light alternating row tint (barely visible gray)
const C_ROW_ALT = [249, 250, 251] as const

// Chapter title order used for Table of Contents
const CHAPTERS = [
    'Health Check Results',
    'Data Points',
    'Port Connectivity',
    'Network Diagrams',
] as const

// Severity sort order: worst first, not_applicable last
const SEVERITY_ORDER: Record<string, number> = {
    unhealthy:      0,
    warning:        1,
    gather_failure: 2,
    healthy:        3,
    not_applicable: 4,
}

// Type aliases

type RGB = readonly [number, number, number]

// Rendering context holds all mutable state for one PDF generation run.
// Created fresh inside download_report so concurrent calls are fully isolated.
interface RenderCtx {
    doc: jsPDF
    y: number
}

// Low-level drawing helpers

/**
 * Set the active fill color from an RGB triple.
 */
function set_fill(ctx: RenderCtx, rgb: RGB): void {
    ctx.doc.setFillColor(rgb[0], rgb[1], rgb[2])
}

/**
 * Set the active draw/stroke color from an RGB triple.
 */
function set_draw(ctx: RenderCtx, rgb: RGB): void {
    ctx.doc.setDrawColor(rgb[0], rgb[1], rgb[2])
}

/**
 * Set the active text color from an RGB triple.
 */
function set_text_color(ctx: RenderCtx, rgb: RGB): void {
    ctx.doc.setTextColor(rgb[0], rgb[1], rgb[2])
}

/**
 * Draw a solid filled rectangle.
 */
function fill_rect(ctx: RenderCtx, x: number, y_pos: number, w: number, h: number, color: RGB): void {
    set_fill(ctx, color)
    ctx.doc.rect(x, y_pos, w, h, 'F')
}

/**
 * Draw a solid filled rounded rectangle (pill shape).
 */
function fill_rounded_rect(ctx: RenderCtx, x: number, y_pos: number, w: number, h: number, r: number, color: RGB): void {
    set_fill(ctx, color)
    ctx.doc.roundedRect(x, y_pos, w, h, r, r, 'F')
}

/**
 * Draw a thin horizontal rule across the printable area.
 */
function draw_rule(ctx: RenderCtx, y_pos: number, color: RGB = [220, 220, 220]): void {
    set_draw(ctx, color)
    ctx.doc.setLineWidth(0.2)
    ctx.doc.line(MARGIN, y_pos, MARGIN + CONTENT_W, y_pos)
}

// Page management

/**
 * Add a new page and reset the y cursor to the top margin.
 */
function new_page(ctx: RenderCtx): void {
    ctx.doc.addPage()
    ctx.y = MARGIN_T
}

/**
 * If fewer than `needed_mm` remain before the bottom margin, start a new page.
 * Returns true if a new page was added.
 */
function ensure_space(ctx: RenderCtx, needed_mm: number): boolean {
    if (ctx.y + needed_mm > Y_MAX) {
        new_page(ctx)
        return true
    }
    return false
}

// Status palette helpers

/**
 * Resolve foreground and background badge colors for a given check status string.
 */
function badge_colors(status: string): { fg: RGB; bg: RGB } {
    if (status === 'healthy')         return { fg: C_GREEN, bg: CB_GREEN }
    if (status === 'warning')         return { fg: C_AMBER, bg: CB_AMBER }
    if (status === 'unhealthy')       return { fg: C_RED,   bg: CB_RED   }
    if (status === 'gather_failure')  return { fg: C_AMBER, bg: CB_AMBER }
    // not_applicable and unknown
    return { fg: C_GRAY, bg: CB_GRAY }
}

/**
 * Short display label for a status value (e.g. "not_applicable" → "N/A").
 */
function badge_label(status: string): string {
    if (status === 'not_applicable') return 'N/A'
    if (status === 'gather_failure') return 'GATHER FAIL'
    return status.toUpperCase()
}

/**
 * Port status badge colors (slightly different palette than check statuses).
 */
function port_badge_colors(status: string): { fg: RGB; bg: RGB } {
    if (status === 'open')     return { fg: C_GREEN, bg: CB_GREEN }
    if (status === 'closed')   return { fg: C_RED,   bg: CB_RED   }
    if (status === 'filtered') return { fg: C_AMBER, bg: CB_AMBER }
    // error and unknown
    return { fg: C_GRAY, bg: CB_GRAY }
}

// Badge drawing

/**
 * Draw a filled pill badge at the given position and return its width in mm.
 * The pill is sized to fit the label text with horizontal padding.
 *
 * @param ctx       Active render context
 * @param x         Left edge of the badge
 * @param y_pos     Baseline y of the badge text (center of pill is offset upward)
 * @param label     Text displayed inside the pill
 * @param fg        Text colour
 * @param bg        Background fill colour
 * @param font_size Font size in pt (default 7)
 * @returns Width of the rendered badge in mm
 */
function draw_badge(
    ctx: RenderCtx,
    x: number,
    y_pos: number,
    label: string,
    fg: RGB,
    bg: RGB,
    font_size = 7,
): number {
    ctx.doc.setFontSize(font_size)
    ctx.doc.setFont('helvetica', 'bold')

    const text_w   = ctx.doc.getTextWidth(label)
    const pad_h    = 1.2  // horizontal padding inside pill
    const pad_v    = 0.8  // vertical padding inside pill
    const pill_h   = font_size * 0.353 + pad_v * 2  // approx mm per pt * font_size
    const pill_w   = text_w + pad_h * 2

    // Draw background pill y_pos is text baseline so shift up by font height + padding
    fill_rounded_rect(ctx, x, y_pos - pill_h + pad_v, pill_w, pill_h, 1, bg)

    // Draw label text on top
    set_text_color(ctx, fg)
    ctx.doc.text(label, x + pad_h, y_pos)

    ctx.doc.setFont('helvetica', 'normal')
    return pill_w
}

// Chapter heading

/**
 * Render a Wire-blue chapter heading with a left accent bar.
 * Advances ctx.y by the heading height plus spacing.
 *
 * @param ctx        Active render context
 * @param title      Chapter title text
 * @param chapter_n  Chapter number displayed to the right (e.g. "Chapter 1")
 */
function draw_chapter_heading(ctx: RenderCtx, title: string, chapter_n: number): void {
    ensure_space(ctx, 20)

    // Blue accent bar on the left edge
    fill_rect(ctx, MARGIN, ctx.y, 3, 9, C_BLUE)

    // Chapter label (small, gray, right-aligned)
    ctx.doc.setFontSize(8)
    ctx.doc.setFont('helvetica', 'normal')
    set_text_color(ctx, C_GRAY)
    ctx.doc.text(`Chapter ${chapter_n}`, MARGIN + CONTENT_W, ctx.y + 3, { align: 'right' })

    // Chapter title text
    ctx.doc.setFontSize(16)
    ctx.doc.setFont('helvetica', 'bold')
    set_text_color(ctx, C_BLUE)
    ctx.doc.text(title, MARGIN + 5, ctx.y + 7)

    ctx.y += 14

    // Thin separator under the heading
    draw_rule(ctx, ctx.y, [190, 210, 240])
    ctx.y += 5
}

// Markdown-to-plain-text conversion

// Isolated marked instance for PDF text extraction
const pdf_md = new Marked({ gfm: true, breaks: true })

/**
 * Convert recommendation text (which may contain Markdown and/or HTML tags)
 * into clean plain text suitable for jsPDF's text() method.
 *
 * Pipeline: markdown → HTML → strip all tags → clean up whitespace.
 * Handles **bold**, `code`, list markers, <command>, <br>, and other formatting.
 */
function markdown_to_plain(text: string): string {
    // First render markdown to HTML so structural tokens (**bold**, `code`, etc.) become tags
    const html = pdf_md.parse(text, { async: false }) as string

    // Preserve structure with newlines for block-level tags, then strip all remaining tags
    const stripped = html
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<\/(?:p|div|li|tr|h[1-6])>/gi, '\n')
        .replace(/<[^>]*>/g, '')

    // Decode all HTML entities (including &mdash;, &hellip;, &rsquo;, &#x27;, etc. that marked
    // may emit for special characters) by letting the browser's HTML parser handle them natively
    const decoded = new DOMParser().parseFromString(stripped, 'text/html').body.textContent ?? ''

    return decoded
        // Collapse runs of whitespace on each line, trim blank lines
        .split('\n')
        .map(line => line.replace(/\s+/g, ' ').trim())
        .filter(line => line.length > 0)
        .join('\n')
        .trim()
}

// Cover page

/**
 * Build the cover page: blue header banner, summary count cards, table of contents.
 *
 * @param ctx           Active render context
 * @param results       Full list of check outputs (for summary counts)
 * @param data_points   Full list of data points (for count)
 * @param port_count    Number of port connectivity rows
 * @param diagram_count Number of network diagrams
 */
function draw_cover_page(
    ctx: RenderCtx,
    results: CheckOutput[],
    data_points: DataPoint[],
    port_count: number,
    diagram_count: number,
): void {
    // Blue header banner
    const banner_h = 55

    fill_rect(ctx, 0, 0, PAGE_W, banner_h, C_BLUE)

    // White title text
    ctx.doc.setFontSize(22)
    ctx.doc.setFont('helvetica', 'bold')
    set_text_color(ctx, C_WHITE)
    ctx.doc.text('Wire Deployment Health Report', PAGE_W / 2, 22, { align: 'center' })

    // White subtitle
    ctx.doc.setFontSize(11)
    ctx.doc.setFont('helvetica', 'normal')
    ctx.doc.text('Fact Gathering Analysis', PAGE_W / 2, 33, { align: 'center' })

    // Generated date (European format YYYY-MM-DD HH:mm:ss, UTC-normalised to match all other timestamps)
    const date_str = format_timestamp(new Date().toISOString())
    ctx.doc.setFontSize(9)
    set_text_color(ctx, [180, 210, 255])
    ctx.doc.text(`Generated: ${date_str}`, PAGE_W / 2, 44, { align: 'center' })

    ctx.y = banner_h + 14

    // Summary count cards
    const count = (s: string) => results.filter(r => r.status === s).length
    const total         = results.length
    const healthy       = count('healthy')
    const warning       = count('warning')
    const unhealthy     = count('unhealthy')
    const gather_fail   = count('gather_failure')
    const not_applicable = count('not_applicable')

    // Build the card definitions (skip gather_failure card when zero)
    type Card = { label: string; value: number; fg: RGB; bg: RGB }
    const cards: Card[] = [
        { label: 'Total',          value: total,          fg: C_DARK,  bg: CB_BLUE  },
        { label: 'Healthy',        value: healthy,        fg: C_GREEN, bg: CB_GREEN },
        { label: 'Warnings',       value: warning,        fg: C_AMBER, bg: CB_AMBER },
        { label: 'Unhealthy',      value: unhealthy,      fg: C_RED,   bg: CB_RED   },
    ]
    if (gather_fail > 0) {
        cards.push({ label: 'Gather Failures', value: gather_fail, fg: C_AMBER, bg: CB_AMBER })
    }
    cards.push({ label: 'Not Tested', value: not_applicable, fg: C_GRAY, bg: CB_GRAY })

    const card_w     = (CONTENT_W - (cards.length - 1) * 3) / cards.length
    const card_h     = 20
    const card_y     = ctx.y

    for (let index = 0; index < cards.length; index++) {
        const card    = cards[index]!
        const card_x  = MARGIN + index * (card_w + 3)

        // Card background rounded rectangle
        fill_rounded_rect(ctx, card_x, card_y, card_w, card_h, 2, card.bg)

        // Count number (large)
        ctx.doc.setFontSize(18)
        ctx.doc.setFont('helvetica', 'bold')
        set_text_color(ctx, card.fg)
        ctx.doc.text(String(card.value), card_x + card_w / 2, card_y + 11, { align: 'center' })

        // Label (small, below count)
        ctx.doc.setFontSize(7)
        ctx.doc.setFont('helvetica', 'normal')
        set_text_color(ctx, C_GRAY)
        ctx.doc.text(card.label, card_x + card_w / 2, card_y + 17, { align: 'center' })
    }

    ctx.y = card_y + card_h + 14

    // Table of contents
    ctx.doc.setFontSize(12)
    ctx.doc.setFont('helvetica', 'bold')
    set_text_color(ctx, C_DARK)
    ctx.doc.text('Contents', MARGIN, ctx.y)
    ctx.y += 8

    draw_rule(ctx, ctx.y)
    ctx.y += 4

    // Chapter 1: Health Checks
    draw_toc_row(ctx, 1, CHAPTERS[0], `${results.length} checks`)
    // Chapter 2: Data Points
    draw_toc_row(ctx, 2, CHAPTERS[1], `${data_points.length} data points`)
    // Chapter 3: Port Connectivity
    draw_toc_row(ctx, 3, CHAPTERS[2], port_count > 0 ? `${port_count} connections` : 'No data')
    // Chapter 4: Network Diagrams
    draw_toc_row(ctx, 4, CHAPTERS[3], diagram_count > 0 ? `${diagram_count} nodes` : 'No data')
}

/**
 * Render a single table-of-contents row with dot leaders.
 */
function draw_toc_row(ctx: RenderCtx, n: number, title: string, detail: string): void {
    const row_h = 10

    // Alternating background for readability
    if (n % 2 === 0) {
        fill_rect(ctx, MARGIN, ctx.y - 1, CONTENT_W, row_h, C_ROW_ALT)
    }

    // Chapter number bullet
    ctx.doc.setFontSize(9)
    ctx.doc.setFont('helvetica', 'bold')
    set_text_color(ctx, C_BLUE)
    ctx.doc.text(`${n}`, MARGIN + 2, ctx.y + 5)

    // Chapter title
    ctx.doc.setFont('helvetica', 'normal')
    set_text_color(ctx, C_DARK)
    ctx.doc.text(title, MARGIN + 10, ctx.y + 5)

    // Right-aligned detail
    set_text_color(ctx, C_GRAY)
    ctx.doc.text(detail, MARGIN + CONTENT_W, ctx.y + 5, { align: 'right' })

    ctx.y += row_h
}

// Chapter 1: Health check results

/**
 * Render Chapter 1: Health Check Results grouped by category.
 * Categories are sorted alphabetically. Within each category, checks are
 * sorted by severity with unhealthy first and not_applicable last.
 */
function draw_chapter_health(ctx: RenderCtx, results: CheckOutput[]): void {
    new_page(ctx)
    draw_chapter_heading(ctx, CHAPTERS[0], 1)

    if (results.length === 0) {
        draw_empty_state(ctx, 'No health check results available.')
        return
    }

    // Group results by category
    const categories = new Map<string, CheckOutput[]>()
    for (const r of results) {
        const group = categories.get(r.category) ?? []
        group.push(r)
        categories.set(r.category, group)
    }

    // Sort categories alphabetically
    const sorted_cats = [...categories.keys()].sort()

    for (const cat of sorted_cats) {
        const items = categories.get(cat)!

        // Sort within category: worst status first
        const sorted_items = [...items].sort((a, b) =>
            (SEVERITY_ORDER[a.status] ?? 4) - (SEVERITY_ORDER[b.status] ?? 4)
        )

        // Compute worst status badge for this category
        const worst = sorted_items[0]?.status ?? 'not_applicable'
        const summary_parts: string[] = []
        const s_count = (s: string) => sorted_items.filter(r => r.status === s).length
        const h = s_count('healthy'), w = s_count('warning'), u = s_count('unhealthy')
        const gf = s_count('gather_failure'), na = s_count('not_applicable')
        if (u > 0) summary_parts.push(`${u} unhealthy`)
        if (w > 0) summary_parts.push(`${w} warning`)
        if (gf > 0) summary_parts.push(`${gf} gather fail`)
        if (h > 0) summary_parts.push(`${h} healthy`)
        if (na > 0) summary_parts.push(`${na} N/A`)
        const summary_str = summary_parts.join(', ')

        // Category group header needs ~12mm
        ensure_space(ctx, 12)

        // Left accent bar
        fill_rect(ctx, MARGIN, ctx.y, 2.5, 8, C_BLUE)

        // Category name (bold)
        ctx.doc.setFontSize(10)
        ctx.doc.setFont('helvetica', 'bold')
        set_text_color(ctx, C_DARK)
        ctx.doc.text(cat, MARGIN + 5, ctx.y + 5.5)

        // Summary text (right-aligned, gray)
        ctx.doc.setFontSize(8)
        ctx.doc.setFont('helvetica', 'normal')
        set_text_color(ctx, C_GRAY)

        // Reserve space for the worst-status badge on far right
        const { fg: wfg, bg: wbg } = badge_colors(worst)
        const badge_lbl = badge_label(worst)
        ctx.doc.setFontSize(7)
        ctx.doc.setFont('helvetica', 'bold')
        const badge_text_w = ctx.doc.getTextWidth(badge_lbl)
        const badge_total_w = badge_text_w + 2.4 + 2  // padding + some breathing room

        ctx.doc.setFontSize(8)
        ctx.doc.setFont('helvetica', 'normal')
        set_text_color(ctx, C_GRAY)
        ctx.doc.text(summary_str, MARGIN + CONTENT_W - badge_total_w - 2, ctx.y + 5.5, { align: 'right' })

        // Draw worst-status badge
        draw_badge(ctx, MARGIN + CONTENT_W - badge_total_w + 1, ctx.y + 6, badge_lbl, wfg, wbg, 7)

        ctx.y += 10

        // Separator under category header
        draw_rule(ctx, ctx.y, [220, 230, 245])
        ctx.y += 2

        // Render each check row
        for (let idx = 0; idx < sorted_items.length; idx++) {
            const r = sorted_items[idx]
            draw_check_row(ctx, r!, idx % 2 === 1)
        }

        ctx.y += 4  // spacing between categories
    }
}

/**
 * Render a single check result row with status badge, name, value, and recommendation.
 *
 * @param ctx    Active render context
 * @param r      The check output to render
 * @param shaded Whether to draw the alternating-row background tint
 */
function draw_check_row(ctx: RenderCtx, r: CheckOutput, shaded: boolean): void {
    const { fg, bg } = badge_colors(r.status)
    const label      = badge_label(r.status)
    const value_str  = r.display_value !== undefined ? format_value(r.display_value, r.display_unit) : ''

    // Calculate recommendation lines to size the row
    const rec_text     = r.recommendation ? markdown_to_plain(r.recommendation) : ''
    const rec_col_x    = MARGIN + 3    // recommendation indented under check name
    const rec_max_w    = CONTENT_W - 3
    const rec_lines    = rec_text
        ? ctx.doc.splitTextToSize(rec_text, rec_max_w)
        : []
    const line_h       = 4.0           // mm per recommendation line
    const row_h        = 7 + (rec_lines.length > 0 ? rec_lines.length * line_h + 1 : 0)

    // Guard: ensure the entire row fits on current page
    ensure_space(ctx, row_h + 1)

    // Alternating background
    if (shaded) {
        fill_rect(ctx, MARGIN, ctx.y, CONTENT_W, row_h, C_ROW_ALT)
    }

    // Status badge pill
    const badge_w = draw_badge(ctx, MARGIN + 1, ctx.y + 5.5, label, fg, bg, 7)

    // Check name
    const name_x = MARGIN + badge_w + 3
    ctx.doc.setFontSize(9)
    ctx.doc.setFont('helvetica', 'normal')
    set_text_color(ctx, C_DARK)

    // Truncate name if needed to leave room for value; cap value width to prevent negative name space
    const max_value_w   = CONTENT_W * 0.4
    const raw_value_w   = value_str ? ctx.doc.getTextWidth(value_str) + 4 : 0
    const capped_value_w = Math.min(raw_value_w, max_value_w)
    const name_max_w    = Math.max(CONTENT_W - badge_w - 4 - capped_value_w, 30)
    const check_name    = ctx.doc.splitTextToSize(r.name, name_max_w)[0] ?? r.name
    ctx.doc.text(check_name, name_x, ctx.y + 5.5)

    // Value (right-aligned, blue tint); truncate with ellipsis if it exceeds the capped width
    if (value_str) {
        ctx.doc.setFontSize(8.5)
        set_text_color(ctx, C_BLUE)
        let display_val = value_str
        if (raw_value_w > max_value_w) {
            display_val = ctx.doc.splitTextToSize(value_str, max_value_w - 4)[0] ?? value_str
            if (display_val.length < value_str.length) display_val += '\u2026'
        }
        ctx.doc.text(display_val, MARGIN + CONTENT_W, ctx.y + 5.5, { align: 'right' })
    }

    // Recommendation (indented, gray, smaller font)
    if (rec_lines.length > 0) {
        ctx.doc.setFontSize(7.5)
        ctx.doc.setFont('helvetica', 'italic')
        set_text_color(ctx, C_GRAY)
        for (let line_i = 0; line_i < rec_lines.length; line_i++) {
            ctx.doc.text(rec_lines[line_i], rec_col_x, ctx.y + 8 + line_i * line_h)
        }
        ctx.doc.setFont('helvetica', 'normal')
    }

    ctx.y += row_h
}

// Chapter 2: Data points

/**
 * Render Chapter 2: Data Points grouped by top-level and second-level path segment.
 * Paths follow the pattern «top/sub/.../leaf» we group by first two segments.
 */
function draw_chapter_data(ctx: RenderCtx, data_points: DataPoint[]): void {
    new_page(ctx)
    draw_chapter_heading(ctx, CHAPTERS[1], 2)

    if (data_points.length === 0) {
        draw_empty_state(ctx, 'No data points available.')
        return
    }

    // Group by first path segment (top-level category)
    const top_groups = new Map<string, DataPoint[]>()
    for (const dp of data_points) {
        const segments = dp.path.split('/')
        const top      = segments[0] ?? 'other'
        const group    = top_groups.get(top) ?? []
        group.push(dp)
        top_groups.set(top, group)
    }

    // Sort top-level groups alphabetically
    const sorted_tops = [...top_groups.keys()].sort()

    for (const top of sorted_tops) {
        const items = top_groups.get(top)!

        // Top-level group header needs ~12mm
        ensure_space(ctx, 12)

        // Blue left accent bar
        fill_rect(ctx, MARGIN, ctx.y, 2.5, 7, C_BLUE)

        ctx.doc.setFontSize(10)
        ctx.doc.setFont('helvetica', 'bold')
        set_text_color(ctx, C_DARK)
        ctx.doc.text(top, MARGIN + 5, ctx.y + 5)

        // Right-aligned item count
        ctx.doc.setFontSize(8)
        ctx.doc.setFont('helvetica', 'normal')
        set_text_color(ctx, C_GRAY)
        ctx.doc.text(`${items.length} data points`, MARGIN + CONTENT_W, ctx.y + 5, { align: 'right' })

        ctx.y += 9
        draw_rule(ctx, ctx.y, [220, 230, 245])
        ctx.y += 3

        // Sub-group by second path segment
        const sub_groups = new Map<string, DataPoint[]>()
        for (const dp of items) {
            const segments = dp.path.split('/')
            const sub      = segments.length > 2 ? (segments[1] ?? '') : ''
            const sg       = sub_groups.get(sub) ?? []
            sg.push(dp)
            sub_groups.set(sub, sg)
        }

        const sorted_subs = [...sub_groups.keys()].sort()

        for (const sub of sorted_subs) {
            const sub_items = sub_groups.get(sub)!

            // Sub-group label (only if non-empty sub-segment)
            if (sub) {
                ensure_space(ctx, 8)
                ctx.doc.setFontSize(8.5)
                ctx.doc.setFont('helvetica', 'bold')
                set_text_color(ctx, [80, 100, 130])
                ctx.doc.text(sub, MARGIN + 3, ctx.y + 4)
                ctx.y += 6
            }

            // Column header row (once per sub-group)
            ensure_space(ctx, 8)
            fill_rect(ctx, MARGIN, ctx.y, CONTENT_W, 6, [235, 240, 250])
            ctx.doc.setFontSize(7.5)
            ctx.doc.setFont('helvetica', 'bold')
            set_text_color(ctx, C_GRAY)
            const dl = data_col_layout()
            ctx.doc.text('PATH',        MARGIN + dl.path_x + 2,       ctx.y + 4)
            ctx.doc.text('VALUE',       MARGIN + dl.value_x,          ctx.y + 4)
            ctx.doc.text('DESCRIPTION', MARGIN + dl.desc_x,           ctx.y + 4)
            ctx.y += 7

            for (let idx = 0; idx < sub_items.length; idx++) {
                draw_data_point_row(ctx, sub_items[idx]!, idx % 2 === 1)
            }

            ctx.y += 2
        }

        ctx.y += 4
    }
}

/**
 * Returns x-offsets and widths for each column in the data-point table (Chapter 2).
 * Shared between draw_chapter_data() header row and draw_data_point_row().
 */
function data_col_layout(): { path_x: number; path_w: number; value_x: number; value_w: number; desc_x: number; desc_w: number } {
    const path_w = CONTENT_W * 0.52
    const value_w = CONTENT_W * 0.17
    const desc_w = CONTENT_W * 0.31
    return {
        path_x:  0,
        path_w,
        value_x: path_w,
        value_w,
        desc_x:  path_w + value_w,
        desc_w,
    }
}

/**
 * Render a single data point as a three-column row: path leaf, value, description.
 */
function draw_data_point_row(ctx: RenderCtx, dp: DataPoint, shaded: boolean): void {
    const row_h = 6.5

    ensure_space(ctx, row_h + 1)

    if (shaded) {
        fill_rect(ctx, MARGIN, ctx.y, CONTENT_W, row_h, C_ROW_ALT)
    }

    // Extract the leaf path segment (last segment after /)
    const segments  = dp.path.split('/')
    const leaf_name = segments[segments.length - 1] ?? dp.path

    // Column layout shared with header row
    const dl = data_col_layout()

    ctx.doc.setFontSize(8)
    ctx.doc.setFont('helvetica', 'normal')

    // Path leaf (slightly indented, dark)
    set_text_color(ctx, C_DARK)
    const path_text = ctx.doc.splitTextToSize(leaf_name, dl.path_w - 3)[0] ?? leaf_name
    ctx.doc.text(path_text, MARGIN + dl.path_x + 2, ctx.y + 4.5)

    // Value (blue, truncated)
    const val_str  = format_value(dp.value, dp.unit)
    set_text_color(ctx, C_BLUE)
    const val_text = ctx.doc.splitTextToSize(val_str, dl.value_w - 2)[0] ?? val_str
    ctx.doc.text(val_text, MARGIN + dl.value_x, ctx.y + 4.5)

    // Description (gray, truncated)
    set_text_color(ctx, C_GRAY)
    const desc_text = ctx.doc.splitTextToSize(dp.description, dl.desc_w - 2)[0] ?? dp.description
    ctx.doc.text(desc_text, MARGIN + dl.desc_x, ctx.y + 4.5)

    ctx.y += row_h
}

// Chapter 3: Port connectivity

/**
 * Render Chapter 3: Port Connectivity as a flat sortable table.
 */
function draw_chapter_ports(ctx: RenderCtx, port_results: PortCheckResult[]): void {
    new_page(ctx)
    draw_chapter_heading(ctx, CHAPTERS[2], 3)

    if (port_results.length === 0) {
        draw_empty_state(ctx, 'No port connectivity data available. Run the gatherer with port scanning enabled.')
        return
    }

    // Summary stat row
    const n_open     = port_results.filter(r => r.status === 'open').length
    const n_closed   = port_results.filter(r => r.status === 'closed').length
    const n_filtered = port_results.filter(r => r.status === 'filtered').length
    const n_error    = port_results.filter(r => r.status === 'error').length

    draw_port_stats(ctx, port_results.length, n_open, n_closed, n_filtered, n_error)
    ctx.y += 6

    // Column header row
    ensure_space(ctx, 8)
    fill_rect(ctx, MARGIN, ctx.y, CONTENT_W, 7, C_BLUE)
    ctx.doc.setFontSize(8)
    ctx.doc.setFont('helvetica', 'bold')
    set_text_color(ctx, C_WHITE)

    // Column positions (fractions of CONTENT_W)
    const cx = port_col_x()
    ctx.doc.text('SOURCE',   MARGIN + cx.source + 1,   ctx.y + 4.5)
    ctx.doc.text('TARGET',   MARGIN + cx.target + 1,   ctx.y + 4.5)
    ctx.doc.text('PORT',     MARGIN + cx.port + 1,     ctx.y + 4.5)
    ctx.doc.text('SERVICE',  MARGIN + cx.service + 1,  ctx.y + 4.5)
    ctx.doc.text('STATUS',   MARGIN + cx.status_col + 1, ctx.y + 4.5)
    ctx.y += 8

    // Sort: source then target then port
    const sorted = [...port_results].sort((a, b) => {
        const src_cmp = a.source_name.localeCompare(b.source_name)
        if (src_cmp !== 0) return src_cmp
        const tgt_cmp = a.target_name.localeCompare(b.target_name)
        if (tgt_cmp !== 0) return tgt_cmp
        return a.port - b.port
    })

    for (let idx = 0; idx < sorted.length; idx++) {
        draw_port_row(ctx, sorted[idx]!, idx % 2 === 1)
    }
}

/**
 * Returns x-offsets for each column in the port table (relative to MARGIN).
 */
function port_col_x(): { source: number; target: number; port: number; service: number; status_col: number } {
    return {
        source:     0,
        target:     CONTENT_W * 0.26,
        port:       CONTENT_W * 0.52,
        service:    CONTENT_W * 0.64,
        status_col: CONTENT_W * 0.84,
    }
}

/**
 * Draw colored summary stat boxes for port connectivity.
 */
function draw_port_stats(
    ctx: RenderCtx,
    total: number,
    open: number,
    closed: number,
    filtered: number,
    error: number,
): void {
    type StatCard = { label: string; value: number; fg: RGB; bg: RGB }
    const cards: StatCard[] = [
        { label: 'Total',    value: total,    fg: C_DARK,  bg: CB_BLUE  },
        { label: 'Open',     value: open,     fg: C_GREEN, bg: CB_GREEN },
        { label: 'Closed',   value: closed,   fg: C_RED,   bg: CB_RED   },
        { label: 'Filtered', value: filtered, fg: C_AMBER, bg: CB_AMBER },
    ]
    if (error > 0) {
        cards.push({ label: 'Error', value: error, fg: C_GRAY, bg: CB_GRAY })
    }

    const card_w = (CONTENT_W - (cards.length - 1) * 2) / cards.length
    const card_h = 16

    for (let index = 0; index < cards.length; index++) {
        const card   = cards[index]!
        const card_x = MARGIN + index * (card_w + 2)

        fill_rounded_rect(ctx, card_x, ctx.y, card_w, card_h, 2, card.bg)

        ctx.doc.setFontSize(14)
        ctx.doc.setFont('helvetica', 'bold')
        set_text_color(ctx, card.fg)
        ctx.doc.text(String(card.value), card_x + card_w / 2, ctx.y + 9, { align: 'center' })

        ctx.doc.setFontSize(6.5)
        ctx.doc.setFont('helvetica', 'normal')
        set_text_color(ctx, C_GRAY)
        ctx.doc.text(card.label, card_x + card_w / 2, ctx.y + 14, { align: 'center' })
    }

    ctx.y += card_h
}

/**
 * Render a single port connectivity row.
 */
function draw_port_row(ctx: RenderCtx, r: PortCheckResult, shaded: boolean): void {
    const row_h = 6.5

    ensure_space(ctx, row_h + 1)

    if (shaded) {
        fill_rect(ctx, MARGIN, ctx.y, CONTENT_W, row_h, C_ROW_ALT)
    }

    const cx = port_col_x()
    ctx.doc.setFontSize(8)
    ctx.doc.setFont('helvetica', 'normal')
    set_text_color(ctx, C_DARK)

    // Source name (may be long truncate)
    const src_max = CONTENT_W * 0.24
    const src_txt = ctx.doc.splitTextToSize(r.source_name, src_max)[0] ?? r.source_name
    ctx.doc.text(src_txt, MARGIN + cx.source + 1, ctx.y + 4.5)

    // Target name
    const tgt_max = CONTENT_W * 0.24
    const tgt_txt = ctx.doc.splitTextToSize(r.target_name, tgt_max)[0] ?? r.target_name
    ctx.doc.text(tgt_txt, MARGIN + cx.target + 1, ctx.y + 4.5)

    // Port / protocol
    set_text_color(ctx, C_BLUE)
    ctx.doc.text(`${r.port}/${r.protocol}`, MARGIN + cx.port + 1, ctx.y + 4.5)

    // Service name
    set_text_color(ctx, C_DARK)
    const svc_max = CONTENT_W * 0.18
    const svc_txt = ctx.doc.splitTextToSize(r.service, svc_max)[0] ?? r.service
    ctx.doc.text(svc_txt, MARGIN + cx.service + 1, ctx.y + 4.5)

    // Status badge
    const { fg, bg } = port_badge_colors(r.status)
    draw_badge(ctx, MARGIN + cx.status_col + 1, ctx.y + 5, r.status.toUpperCase(), fg, bg, 7)

    ctx.y += row_h
}

// Chapter 4: Network diagrams

/**
 * Render Chapter 4: Network Diagrams. Each diagram is an SVG rasterised to PNG
 * via the browser canvas API and embedded as a full-width image.
 *
 * This is async because SVG to PNG conversion uses the Image/canvas API.
 */
async function draw_chapter_diagrams(ctx: RenderCtx, diagrams: { name: string; svg: string }[]): Promise<void> {
    new_page(ctx)
    draw_chapter_heading(ctx, CHAPTERS[3], 4)

    if (diagrams.length === 0) {
        draw_empty_state(ctx, 'No network diagram data available. Run the gatherer with port scanning enabled.')
        return
    }

    // Render each diagram: SVG → PNG dataURL → jsPDF image
    for (let idx = 0; idx < diagrams.length; idx++) {
        const diag = diagrams[idx]!

        // Each diagram gets its own page (after the first)
        if (idx > 0) {
            new_page(ctx)
        } else {
            ensure_space(ctx, 15)
        }

        // Diagram title
        ctx.doc.setFontSize(10)
        ctx.doc.setFont('helvetica', 'bold')
        set_text_color(ctx, C_DARK)
        ctx.doc.text(diag.name, MARGIN, ctx.y + 5)
        ctx.y += 9

        // Convert SVG to PNG using the browser canvas
        try {
            // svg_to_png_data_url gives us the actual aspect ratio from the SVG viewBox,
            // so each diagram gets its correct proportions
            const { data_url, aspect } = await svg_to_png_data_url(diag.svg, 1360)

            const img_w = CONTENT_W
            const img_h = img_w * aspect

            // Start a new page if the image won't fit
            ensure_space(ctx, img_h + 4)

            ctx.doc.addImage(data_url, 'PNG', MARGIN, ctx.y, img_w, img_h)
            ctx.y += img_h + 4
        } catch (err) {
            // If rasterising fails, show a styled error note instead
            ctx.doc.setFontSize(8)
            ctx.doc.setFont('helvetica', 'italic')
            set_text_color(ctx, C_GRAY)
            ctx.doc.text(`Could not render diagram: ${String(err)}`, MARGIN, ctx.y + 4)
            ctx.y += 8
        }
    }
}

// Shared empty-state block

/**
 * Draw a light gray box with an italic note, used when a chapter has no data.
 */
function draw_empty_state(ctx: RenderCtx, message: string): void {
    ensure_space(ctx, 18)

    fill_rounded_rect(ctx, MARGIN, ctx.y, CONTENT_W, 14, 2, CB_GRAY)

    ctx.doc.setFontSize(9)
    ctx.doc.setFont('helvetica', 'italic')
    set_text_color(ctx, C_GRAY)
    ctx.doc.text(message, PAGE_W / 2, ctx.y + 8, { align: 'center' })

    ctx.doc.setFont('helvetica', 'normal')
    ctx.y += 18
}

// Footer

/**
 * Add a footer to every page after all content has been rendered.
 * Must be called last since it uses doc.internal.pages.length to know total pages.
 */
function add_footers(ctx: RenderCtx): void {
    // jsPDF counts pages starting at index 1; index 0 is an internal placeholder
    const total = ctx.doc.internal.pages.length - 1

    for (let page_n = 1; page_n <= total; page_n++) {
        ctx.doc.setPage(page_n)

        // Thin separator line above footer
        set_draw(ctx, [210, 215, 225])
        ctx.doc.setLineWidth(0.2)
        ctx.doc.line(MARGIN, PAGE_H - MARGIN_B + 4, MARGIN + CONTENT_W, PAGE_H - MARGIN_B + 4)

        // Footer text centered
        ctx.doc.setFontSize(7.5)
        ctx.doc.setFont('helvetica', 'normal')
        set_text_color(ctx, C_GRAY)
        ctx.doc.text(
            `Wire Deployment Health Report  ·  Page ${page_n} of ${total}`,
            PAGE_W / 2,
            PAGE_H - MARGIN_B + 10,
            { align: 'center' },
        )
    }
}

// SVG to PNG conversion

/**
 * Rasterise an SVG string to a PNG data URL via a browser canvas element.
 * The SVG is loaded into an <img> via a Blob URL; once loaded it gets drawn
 * onto a canvas at the requested width (height is derived from the viewBox).
 *
 * @param svg_str Complete SVG markup string
 * @param render_w Canvas render width in pixels (height derived from aspect ratio)
 * @returns PNG data URL and the actual height/width aspect ratio from the SVG viewBox
 */
function svg_to_png_data_url(svg_str: string, render_w: number): Promise<{ data_url: string; aspect: number }> {
    return new Promise((resolve, reject) => {
        // Parse viewBox to get aspect ratio each SVG type has its own viewBox dimensions
        const vb_match  = svg_str.match(/viewBox=["']([^"']+)["']/)
        const vb_parts  = vb_match ? vb_match[1]!.split(/\s+/) : ['0', '0', '1400', '835']
        const vb_w      = Math.max(parseFloat(vb_parts[2] ?? '1400') || 1400, 1)
        const vb_h      = Math.max(parseFloat(vb_parts[3] ?? '835') || 835, 1)
        const aspect    = vb_h / vb_w
        const render_h  = Math.round(render_w * aspect)

        // Create Blob URL from SVG text (needs correct MIME type)
        const blob   = new Blob([svg_str], { type: 'image/svg+xml;charset=utf-8' })
        const url    = URL.createObjectURL(blob)

        const img    = new Image()
        img.onload   = () => {
            const canvas    = document.createElement('canvas')
            canvas.width    = render_w
            canvas.height   = render_h
            const ctx_2d    = canvas.getContext('2d')

            if (!ctx_2d) {
                URL.revokeObjectURL(url)
                reject(new Error('Canvas 2D context unavailable'))
                return
            }

            // White background so transparent SVGs don't end up black in the PDF
            ctx_2d.fillStyle = '#ffffff'
            ctx_2d.fillRect(0, 0, render_w, render_h)
            ctx_2d.drawImage(img, 0, 0, render_w, render_h)

            URL.revokeObjectURL(url)
            resolve({ data_url: canvas.toDataURL('image/png'), aspect })
        }

        img.onerror  = () => {
            URL.revokeObjectURL(url)
            reject(new Error(`Failed to load SVG image for "${svg_str.slice(0, 60)}..."`))
        }

        img.src      = url
    })
}

// Port data extraction

/**
 * Scan DataPoint raw_output fields for embedded JSON port results.
 * The gatherer embeds lines like: PORT_RESULTS_JSON:[...]
 * Mirrors the logic in use_ports.ts.
 */
function extract_port_results(data_points: DataPoint[]): PortCheckResult[] {
    const results: PortCheckResult[] = []
    const JSON_PREFIX = 'PORT_RESULTS_JSON:'

    for (const dp of data_points) {
        // Only port connectivity data points; mirrors the regex in use_port_data.ts
        if (!/\/port_connectivity$/.test(dp.path)) continue

        for (const line of (dp.raw_output ?? '').split('\n')) {
            const trimmed = line.trim()
            if (!trimmed.startsWith(JSON_PREFIX)) continue

            try {
                const parsed = JSON.parse(trimmed.slice(JSON_PREFIX.length)) as PortCheckResult[]
                results.push(...parsed)
            } catch {
                // Skip malformed lines partial data is fine
            }
        }
    }

    return results
}

// Diagram SVG builder

/**
 * Build a list of per-node SVG diagrams from port connectivity results.
 * Mirrors the logic in use_port_diagrams.ts but as a plain function, not a composable.
 *
 * @param port_results All port connectivity results
 * @returns Array of { name, svg } objects, one per unique node, sorted by name
 */
function build_diagram_svgs(port_results: PortCheckResult[]): { name: string; svg: string }[] {
    // Collect unique node identities from both sides of every result
    const seen = new Map<string, { name: string; ip: string; type: 'kubenode' | 'datanode' | 'external' }>()

    for (const r of port_results) {
        if (!seen.has(r.source_name)) {
            seen.set(r.source_name, {
                name: r.source_name,
                ip:   r.source_ip,
                // Prefer gatherer-provided type, fall back to connectivity-pattern inference
                type: r.source_type ?? infer_node_type(r.source_name, port_results),
            })
        }
        if (!seen.has(r.target_name)) {
            seen.set(r.target_name, {
                name: r.target_name,
                ip:   r.target_ip,
                type: r.target_type ?? infer_node_type(r.target_name, port_results),
            })
        }
    }

    return Array.from(seen.values())
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((node, index) => {
            // Unique SVG filter ID suffix to avoid filter-id collisions when SVGs share a DOM
            const id_suffix  = `pdf_n${index}_${node.name.replace(/[^a-zA-Z0-9]/g, '_')}`

            // Compute worst status for each port on this node
            const incoming   = worst_status_per_port(port_results.filter(r => r.target_name === node.name))
            const outgoing   = worst_status_per_port(port_results.filter(r => r.source_name === node.name))

            // Defense-in-depth: sanitize SVG before canvas rasterisation,
            // matching the browser rendering path in use_port_diagrams.ts
            const raw_svg = node.type === 'datanode'
                ? render_datanode_svg(node.name, node.ip, incoming, outgoing, id_suffix)
                : node.type === 'external'
                    ? render_external_svg(node.name, node.ip, incoming, outgoing, id_suffix)
                    : render_kubenode_svg(node.name, node.ip, incoming, outgoing, id_suffix)
            const svg = sanitize_svg(raw_svg)

            return { name: node.name, svg }
        })
}

// Public API

/**
 * Generate and trigger download of a professional multi-chapter PDF report.
 *
 * Each call creates its own isolated RenderCtx, so concurrent invocations
 * (e.g. double-click, programmatic re-trigger during an await) cannot corrupt
 * each other's jsPDF instance or y-cursor.
 *
 * Chapters:
 *   1 Health Check Results (categorised, severity-sorted)
 *   2 Data Points (path-hierarchy grouped)
 *   3 Port Connectivity (flat table with stats)
 *   4 Network Diagrams (SVG to PNG via canvas)
 *
 * @param results     Full list of check outputs from the analysis run
 * @param data_points Full list of raw data points collected by the gatherer
 */
export async function download_report(results: CheckOutput[], data_points: DataPoint[]): Promise<void> {
    // Fresh context per call each invocation owns its own jsPDF instance and
    // y-cursor, so a second call cannot overwrite the first call's state even
    // if they interleave at await points inside draw_chapter_diagrams.
    const ctx: RenderCtx = {
        doc: new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' }),
        y:   MARGIN_T,
    }

    // Pre-compute port data so we can pass counts to the cover page
    const port_results  = extract_port_results(data_points)
    const diagrams      = build_diagram_svgs(port_results)

    // Cover page (page 1)
    draw_cover_page(ctx, results, data_points, port_results.length, diagrams.length)

    // Chapter 1
    draw_chapter_health(ctx, results)

    // Chapter 2
    draw_chapter_data(ctx, data_points)

    // Chapter 3
    draw_chapter_ports(ctx, port_results)

    // Chapter 4 (async: canvas SVG to PNG)
    await draw_chapter_diagrams(ctx, diagrams)

    // Footers (must be after all pages exist)
    add_footers(ctx)

    // Trigger browser download
    ctx.doc.save('wire-health-report.pdf')
}
