/**
 * Renders per-node architecture SVGs matching the docs/wire-*-node.svg layout.
 *
 * Each function produces a complete SVG string with port pills and links
 * colored by connectivity status (green=open, red=closed, yellow=filtered,
 * gray=untested). The layout is identical to the static docs SVGs only
 * the title and colors change based on collected data.
 *
 * Functions:
 *   render_kubenode_svg()  re-exported from kubenode_svg.ts
 *   render_datanode_svg()  re-exported from datanode_svg.ts
 */

export { render_kubenode_svg } from './kubenode_svg'

export { render_datanode_svg } from './datanode_svg'

export { render_external_svg } from './external_svg'
