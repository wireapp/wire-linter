/**
 * Renders a simplified external node diagram as SVG.
 *
 * External nodes (load balancers, monitoring agents, external clients) don't run
 * Wire-internal services, so showing brig/galley/etc. boxes would be misleading.
 * This renderer shows only the node identity and port pills for tested connections.
 *
 * Layout: centered node box with incoming port pills on the left and outgoing
 * port pills on the right, no internal service boxes.
 *
 * Functions:
 *   render_external_svg()  simplified external node diagram with port pills
 */

// Ours
import { colors_for_status, esc, render_legend, render_shadow_filter } from './svg_helpers'

/**
 * Collect all ports from a status map and return them sorted ascending.
 * Used to dynamically render port pills for external nodes since we don't
 * know their port set ahead of time (unlike kubenodes/datanodes).
 *
 * @param status_map  Port number to status string map
 * @returns           Sorted array of port numbers
 */
function sorted_ports(status_map: Map<number, string>): number[] {
    return Array.from(status_map.keys()).sort((a, b) => a - b)
}

/**
 * Renders a simplified external node diagram with port pills only.
 *
 * @param node_name       Display name like «load-balancer-1»
 * @param node_ip         IP address
 * @param incoming_status Map of port to status for incoming connections (target = this node)
 * @param outgoing_status Map of port to status for outgoing connections (source = this node)
 * @param id_suffix       Unique suffix for SVG filter IDs to avoid collisions with multiple SVGs
 */
export function render_external_svg(
    node_name: string,
    node_ip: string,
    incoming_status: Map<number, string>,
    outgoing_status: Map<number, string>,
    id_suffix: string,
): string {
    const fid = `sh_${id_suffix}`

    const in_ports  = sorted_ports(incoming_status)
    const out_ports = sorted_ports(outgoing_status)

    // Each port pill is 30px tall (22px pill + 8px gap)
    const pill_h     = 22
    const pill_gap   = 8
    const pill_step  = pill_h + pill_gap
    const max_pills  = Math.max(in_ports.length, out_ports.length, 1)

    // Vertical layout: 42px top for title, 60px box header, pills, 40px legend footer
    const box_top    = 42
    const pills_top  = box_top + 60
    const pills_zone = max_pills * pill_step
    const box_h      = 60 + pills_zone + 20
    const svg_h      = box_top + box_h + 50

    // Horizontal layout: node box centered at 700, pills on the sides
    const box_x = 460
    const box_w = 480

    // Build incoming port pills (left side)
    let in_pills = ''
    for (let i = 0; i < in_ports.length; i++) {
        const port   = in_ports[i]!
        const colors = colors_for_status(incoming_status.get(port))
        const py     = pills_top + i * pill_step

        // Port pill
        in_pills += `<rect x="380" y="${py}" width="72" height="${pill_h}" rx="11" fill="white" stroke="${colors.stroke}" stroke-width="1.4"/>`
        in_pills += `<text x="400" y="${py + 15}" fill="${colors.text}">&#9654; ${port}</text>`

        // Connection line from pill to box edge
        in_pills += `<line x1="452" y1="${py + 11}" x2="${box_x}" y2="${py + 11}" stroke="${colors.link}" stroke-width="1.3" opacity="0.55" fill="none"/>`
    }

    // Build outgoing port pills (right side)
    let out_pills = ''
    const right_pill_x = box_x + box_w + 8
    for (let i = 0; i < out_ports.length; i++) {
        const port   = out_ports[i]!
        const colors = colors_for_status(outgoing_status.get(port))
        const py     = pills_top + i * pill_step

        // Port pill
        out_pills += `<rect x="${right_pill_x}" y="${py}" width="72" height="${pill_h}" rx="11" fill="white" stroke="${colors.stroke}" stroke-width="1.4"/>`
        out_pills += `<text x="${right_pill_x + 14}" y="${py + 15}" fill="${colors.text}">${port} &#9654;</text>`

        // Connection line from box edge to pill
        out_pills += `<line x1="${box_x + box_w}" y1="${py + 11}" x2="${right_pill_x}" y2="${py + 11}" stroke="${colors.link}" stroke-width="1.3" opacity="0.55" fill="none"/>`
    }

    // Empty-state message when no ports were tested
    const no_ports_msg = (in_ports.length === 0 && out_ports.length === 0)
        ? `<text x="700" y="${pills_top + 30}" text-anchor="middle" font-size="11" fill="#94a3b8">No port connectivity data collected</text>`
        : ''

    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 ${svg_h}" font-family="Inter, 'Segoe UI', system-ui, sans-serif" font-size="11">
  ${render_shadow_filter(fid)}

  <rect width="1400" height="${svg_h}" fill="#f8fafc" rx="6"/>
  <text x="700" y="26" text-anchor="middle" font-size="16" font-weight="700" fill="#0f172a">${esc(node_name)} (${esc(node_ip)})</text>

  <!-- External node container -->
  <rect x="${box_x}" y="${box_top}" width="${box_w}" height="${box_h}" rx="14" fill="white" stroke="#94a3b8" stroke-width="1.8" filter="url(#${fid})"/>
  <text x="700" y="${box_top + 24}" text-anchor="middle" font-size="13" font-weight="700" fill="#334155">${esc(node_name)}</text>
  <line x1="${box_x + 14}" y1="${box_top + 32}" x2="${box_x + box_w - 14}" y2="${box_top + 32}" stroke="#e2e8f0"/>

  <!-- Type badge -->
  <rect x="646" y="${box_top + 38}" width="108" height="18" rx="9" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="0.8"/>
  <text x="700" y="${box_top + 51}" text-anchor="middle" font-size="9" font-weight="600" fill="#64748b">EXTERNAL NODE</text>

  <!-- Incoming port pills (left) -->
  <g font-size="9" font-weight="600" font-family="'JetBrains Mono', 'Fira Code', monospace">
    ${in_pills}
  </g>

  <!-- Outgoing port pills (right) -->
  <g font-size="9" font-weight="600" font-family="'JetBrains Mono', 'Fira Code', monospace">
    ${out_pills}
  </g>

  ${no_ports_msg}

  <!-- Legend -->
  ${render_legend(700, svg_h - 15)}

</svg>`
}
