/**
 * Renders a per-node Kubernetes architecture SVG matching the docs/wire-kube-node.svg layout.
 *
 * Produces a complete SVG string with port pills and links colored by connectivity status
 * (green=open, red=closed, yellow=filtered, gray=untested). Covers DMZ/Ingress, Core Services,
 * In-Cluster, and Calling/Media sections with full port pill/link wiring for a Wire kubernetes node.
 *
 * Extracted from node_svg_renderer.ts. The kubenode diagram is a distinct concern from the datanode
 * diagram and is independently navigable here.
 *
 * Functions:
 *   render_kubenode_svg()  full kube node diagram with data-flow coloring
 */

// Ours
import { colors_for_status, esc, render_legend, render_shadow_filter } from './svg_helpers'

/**
 * Renders a Wire Kubernetes Node diagram with port pills and links colored by connectivity status.
 *
 * @param node_name       Display name like «kubenode-1»
 * @param node_ip         IP address
 * @param incoming_status Map of port to status for incoming connections (target = this node)
 * @param outgoing_status Map of port to status for outgoing connections (source = this node)
 * @param id_suffix       Unique suffix for SVG filter IDs to avoid collisions with multiple SVGs
 */
export function render_kubenode_svg(
    node_name: string,
    node_ip: string,
    incoming_status: Map<number, string>,
    outgoing_status: Map<number, string>,
    id_suffix: string,
): string {
    // Get colors for each port pill based on status
    const c443   = colors_for_status(incoming_status.get(443))
    const c3478  = colors_for_status(incoming_status.get(3478))
    const c32768 = colors_for_status(incoming_status.get(32768))

    const c9042  = colors_for_status(outgoing_status.get(9042))
    const c9200  = colors_for_status(outgoing_status.get(9200))
    const c5432  = colors_for_status(outgoing_status.get(5432))
    const c5672  = colors_for_status(outgoing_status.get(5672))
    const c9000  = colors_for_status(outgoing_status.get(9000))
    const c587   = colors_for_status(outgoing_status.get(587))

    const fid = `sh_${id_suffix}`

    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 835" font-family="Inter, 'Segoe UI', system-ui, sans-serif" font-size="11">
  ${render_shadow_filter(fid)}

  <rect width="1400" height="835" fill="#f8fafc" rx="6"/>
  <text x="700" y="26" text-anchor="middle" font-size="16" font-weight="700" fill="#0f172a">${esc(node_name)} (${esc(node_ip)})</text>

  <!-- CENTER: KUBE NODE BOX -->
  <rect x="400" y="42" width="460" height="740" rx="14" fill="white" stroke="#94a3b8" stroke-width="1.8" filter="url(#${fid})"/>
  <text x="630" y="66" text-anchor="middle" font-size="13" font-weight="700" fill="#334155">${esc(node_name)}</text>
  <line x1="415" y1="72" x2="845" y2="72" stroke="#e2e8f0"/>

  <!-- DMZ / INGRESS -->
  <rect x="412" y="78" width="436" height="98" rx="6" fill="#f9fafb" stroke="#e5e7eb" stroke-width="0.8"/>
  <text x="420" y="90" font-size="8" font-weight="600" fill="#9ca3af" letter-spacing="0.5">DMZ / INGRESS</text>
  <rect x="470" y="96" width="220" height="32" rx="5" fill="#fef3c7" stroke="#fbbf24" stroke-width="1.1"/>
  <text x="580" y="116" text-anchor="middle" font-size="10" font-weight="600" fill="#92400e">Nginx Ingress Controller</text>
  <rect x="470" y="136" width="220" height="32" rx="5" fill="#fef3c7" stroke="#fbbf24" stroke-width="1.1"/>
  <text x="485" y="156" font-size="10" font-weight="600" fill="#92400e">nginz</text>
  <text x="530" y="156" font-size="8" fill="#d97706">Wire API gateway</text>

  <!-- CORE SERVICES -->
  <rect x="412" y="184" width="436" height="330" rx="6" fill="#eff6ff" stroke="#dbeafe" stroke-width="0.8"/>
  <text x="420" y="196" font-size="8" font-weight="600" fill="#60a5fa" letter-spacing="0.5">CORE SERVICES</text>
  <rect x="470" y="204" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="224" font-size="10" font-weight="600" fill="#1e40af">brig</text>
  <text x="518" y="224" font-size="8" fill="#60a5fa">auth &amp; accounts</text>
  <rect x="470" y="244" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="264" font-size="10" font-weight="600" fill="#1e40af">galley</text>
  <text x="530" y="264" font-size="8" fill="#60a5fa">conversations</text>
  <rect x="470" y="284" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="304" font-size="10" font-weight="600" fill="#1e40af">gundeck</text>
  <text x="542" y="304" font-size="8" fill="#60a5fa">push &amp; delivery</text>
  <rect x="470" y="324" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="344" font-size="10" font-weight="600" fill="#1e40af">cannon</text>
  <text x="532" y="344" font-size="8" fill="#60a5fa">WebSocket push</text>
  <rect x="470" y="364" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="384" font-size="10" font-weight="600" fill="#1e40af">cargohold</text>
  <text x="549" y="384" font-size="8" fill="#60a5fa">assets / S3</text>
  <rect x="470" y="404" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="424" font-size="10" font-weight="600" fill="#1e40af">spar</text>
  <text x="510" y="424" font-size="8" fill="#60a5fa">SSO &amp; SCIM</text>
  <rect x="470" y="444" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="464" font-size="10" font-weight="600" fill="#1e40af">background-worker</text>
  <text x="610" y="464" font-size="8" fill="#60a5fa">async jobs</text>
  <rect x="470" y="484" width="220" height="32" rx="5" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.1"/>
  <text x="485" y="504" font-size="10" font-weight="600" fill="#1e40af">web-server</text>
  <text x="555" y="504" font-size="8" fill="#60a5fa">webapp assets</text>

  <!-- IN-CLUSTER -->
  <rect x="412" y="522" width="436" height="116" rx="6" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8"/>
  <text x="420" y="534" font-size="8" font-weight="600" fill="#8b5cf6" letter-spacing="0.5">IN-CLUSTER</text>
  <rect x="470" y="542" width="220" height="26" rx="5" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="1"/>
  <text x="580" y="559" text-anchor="middle" font-size="10" font-weight="600" fill="#6d28d9">Redis :6379</text>
  <text x="695" y="559" font-size="7" fill="#a78bfa" opacity="0.7">&#x2190; gundeck, cannon</text>
  <rect x="470" y="574" width="220" height="26" rx="5" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="1"/>
  <text x="580" y="591" text-anchor="middle" font-size="10" font-weight="600" fill="#6d28d9">SQS/SNS fake :443</text>
  <text x="695" y="591" font-size="7" fill="#a78bfa" opacity="0.7">&#x2190; brig, galley, gundeck</text>
  <rect x="470" y="606" width="220" height="26" rx="5" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="1"/>
  <text x="580" y="623" text-anchor="middle" font-size="10" font-weight="600" fill="#6d28d9">etcd :2379</text>
  <text x="695" y="623" font-size="7" fill="#a78bfa" opacity="0.7">&#x2190; k8s API server</text>

  <!-- CALLING / MEDIA -->
  <rect x="412" y="646" width="436" height="128" rx="6" fill="#fffbeb" stroke="#fde68a" stroke-width="0.8"/>
  <text x="420" y="658" font-size="8" font-weight="600" fill="#d97706" letter-spacing="0.5">CALLING / MEDIA</text>
  <rect x="470" y="666" width="220" height="32" rx="5" fill="#fef9c3" stroke="#facc15" stroke-width="1.1"/>
  <text x="485" y="686" font-size="10" font-weight="600" fill="#854d0e">coturn</text>
  <text x="530" y="686" font-size="8" fill="#ca8a04">STUN/TURN relay</text>
  <rect x="470" y="706" width="220" height="32" rx="5" fill="#fef9c3" stroke="#facc15" stroke-width="1.1"/>
  <text x="485" y="726" font-size="10" font-weight="600" fill="#854d0e">SFT</text>
  <text x="510" y="726" font-size="8" fill="#ca8a04">selective fwd (conference)</text>
  <rect x="470" y="746" width="220" height="26" rx="5" fill="#fef9c3" stroke="#facc15" stroke-width="1.1"/>
  <text x="485" y="763" font-size="10" font-weight="600" fill="#854d0e">sftd-join-call</text>
  <text x="578" y="763" font-size="8" fill="#ca8a04">call coordination</text>

  <!-- LEFT PORT PILLS (inbound) -->
  <g font-size="9" font-weight="600" font-family="'JetBrains Mono', 'Fira Code', monospace">
    <rect x="364" y="119" width="72" height="22" rx="11" fill="white" stroke="${c443.stroke}" stroke-width="1.4"/>
    <text x="386" y="134" fill="${c443.text}">&#9654; 443</text>
    <rect x="364" y="671" width="72" height="22" rx="11" fill="white" stroke="${c3478.stroke}" stroke-width="1.4"/>
    <text x="380" y="686" fill="${c3478.text}">&#9654; 3478</text>
    <rect x="336" y="711" width="128" height="22" rx="11" fill="white" stroke="${c32768.stroke}" stroke-width="1.4"/>
    <text x="356" y="726" fill="${c32768.text}">&#9654; 32768-65535</text>
  </g>

  <!-- RIGHT PORT PILLS (outbound to data nodes) -->
  <g font-size="9" font-weight="600" font-family="'JetBrains Mono', 'Fira Code', monospace">
    <rect x="824" y="209" width="72" height="22" rx="11" fill="white" stroke="${c9042.stroke}" stroke-width="1.4"/>
    <text x="838" y="224" fill="${c9042.text}">9042 &#9654;</text>
    <rect x="824" y="259" width="72" height="22" rx="11" fill="white" stroke="${c9200.stroke}" stroke-width="1.4"/>
    <text x="838" y="274" fill="${c9200.text}">9200 &#9654;</text>
    <rect x="824" y="309" width="72" height="22" rx="11" fill="white" stroke="${c5432.stroke}" stroke-width="1.4"/>
    <text x="838" y="324" fill="${c5432.text}">5432 &#9654;</text>
    <rect x="824" y="359" width="72" height="22" rx="11" fill="white" stroke="${c5672.stroke}" stroke-width="1.4"/>
    <text x="838" y="374" fill="${c5672.text}">5672 &#9654;</text>
    <rect x="824" y="409" width="72" height="22" rx="11" fill="white" stroke="${c9000.stroke}" stroke-width="1.4"/>
    <text x="838" y="424" fill="${c9000.text}">9000 &#9654;</text>
    <rect x="824" y="459" width="72" height="22" rx="11" fill="white" stroke="${c587.stroke}" stroke-width="1.4"/>
    <text x="842" y="474" fill="${c587.text}">587 &#9654;</text>
  </g>

  <!-- INTERNAL: left pills -> services -->
  <g fill="none">
    <path d="M 436,130 H 456 a 4,4 0 0 0 4,-4 V 116 a 4,4 0 0 1 4,-4 H 470" stroke="${c443.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="436" y1="682" x2="470" y2="682" stroke="${c3478.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="464" y1="722" x2="470" y2="722" stroke="${c32768.link}" stroke-width="1.3" opacity="0.55"/>
  </g>

  <!-- INTERNAL: services -> right port pills (per-link coloring) -->
  <g fill="none">
    <!-- brig -> :9042 DIRECT -->
    <path d="M 690,220 H 824" stroke="${c9042.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- brig -> :9200 -->
    <path d="M 690,212 H 806 a 4,4 0 0 1 4,4 V 266 a 4,4 0 0 0 4,4 H 824" stroke="${c9200.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- brig -> :5432 -->
    <path d="M 690,228 H 786 a 4,4 0 0 1 4,4 V 314 a 4,4 0 0 0 4,4 H 824" stroke="${c5432.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- brig -> :5672 -->
    <path d="M 690,232 H 756 a 4,4 0 0 1 4,4 V 364 a 4,4 0 0 0 4,4 H 824" stroke="${c5672.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- brig -> :587 -->
    <path d="M 690,234 H 811 a 4,4 0 0 1 4,4 V 466 a 4,4 0 0 0 4,4 H 824" stroke="${c587.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- galley -> :9042 -->
    <path d="M 690,256 H 726 a 4,4 0 0 0 4,-4 V 217 a 4,4 0 0 1 4,-4 H 824" stroke="${c9042.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- galley -> :5432 -->
    <path d="M 690,260 H 796 a 4,4 0 0 1 4,4 V 318 a 4,4 0 0 0 4,4 H 824" stroke="${c5432.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- galley -> :5672 -->
    <path d="M 690,264 H 766 a 4,4 0 0 1 4,4 V 366 a 4,4 0 0 0 4,4 H 824" stroke="${c5672.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- gundeck -> :9042 -->
    <path d="M 690,300 H 716 a 4,4 0 0 0 4,-4 V 219 a 4,4 0 0 1 4,-4 H 824" stroke="${c9042.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- spar -> :9042 -->
    <path d="M 690,420 H 706 a 4,4 0 0 0 4,-4 V 229 a 4,4 0 0 1 4,-4 H 824" stroke="${c9042.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- bg-worker -> :9042 -->
    <path d="M 690,457 H 696 a 4,4 0 0 0 4,-4 V 231 a 4,4 0 0 1 4,-4 H 824" stroke="${c9042.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- bg-worker -> :5672 -->
    <path d="M 690,463 H 746 a 4,4 0 0 0 4,-4 V 376 a 4,4 0 0 1 4,-4 H 824" stroke="${c5672.link}" stroke-width="1.1" opacity="0.45"/>
    <!-- cargohold -> :9000 -->
    <path d="M 690,380 H 816 a 4,4 0 0 1 4,4 V 416 a 4,4 0 0 0 4,4 H 824" stroke="${c9000.link}" stroke-width="1.1" opacity="0.45"/>
  </g>

  <!-- INTERNAL: adjacency links (always green - internal, not port-tested) -->
  <g stroke="#22c55e" stroke-width="1.3" opacity="0.55" fill="none">
    <line x1="580" y1="128" x2="580" y2="136"/>
    <line x1="580" y1="738" x2="580" y2="746"/>
  </g>

  <!-- INTERNAL: nginz distribution bus (indigo - internal routing) -->
  <g stroke="#818cf8" stroke-width="1" opacity="0.35" fill="none">
    <path d="M 470,152 H 462 a 4,4 0 0 0 -4,4 V 420"/>
    <line x1="458" y1="220" x2="470" y2="220"/>
    <line x1="458" y1="260" x2="470" y2="260"/>
    <line x1="458" y1="300" x2="470" y2="300"/>
    <line x1="458" y1="340" x2="470" y2="340"/>
    <line x1="458" y1="380" x2="470" y2="380"/>
    <line x1="458" y1="420" x2="470" y2="420"/>
  </g>

  <!-- LEFT SIDE: Clients + Load Balancer -->
  <rect x="30" y="86" width="220" height="36" rx="6" fill="#e0f2fe" stroke="#7dd3fc" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="104" font-size="10" font-weight="600" fill="#0369a1">Clients</text>
  <text x="96" y="104" font-size="8" fill="#38bdf8">browsers, mobile, desktop</text>
  <text x="44" y="116" font-size="7.5" fill="#7dd3fc">HTTPS, WebSocket, STUN, media</text>
  <rect x="30" y="132" width="220" height="32" rx="6" fill="#fef3c7" stroke="#fbbf24" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="151" font-size="10" font-weight="600" fill="#92400e">Load Balancer</text>
  <text x="140" y="151" font-size="8" fill="#d97706">TLS termination</text>

  <!-- LEFT LINKS (per-port coloring) -->
  <g fill="none">
    <line x1="140" y1="122" x2="140" y2="132" stroke="#22c55e" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,148 H 310 a 4,4 0 0 0 4,-4 V 134 a 4,4 0 0 1 4,-4 H 364" stroke="${c443.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,104 H 286 a 4,4 0 0 1 4,4 V 678 a 4,4 0 0 0 4,4 H 364" stroke="${c3478.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,110 H 278 a 4,4 0 0 1 4,4 V 718 a 4,4 0 0 0 4,4 H 336" stroke="${c32768.link}" stroke-width="1.3" opacity="0.6"/>
  </g>

  <!-- RIGHT SIDE: Data Nodes + Mail Server -->
  <rect x="1000" y="270" width="220" height="80" rx="8" fill="#f0fdf4" stroke="#86efac" stroke-width="1.3" filter="url(#${fid})"/>
  <text x="1110" y="296" text-anchor="middle" font-size="11" font-weight="700" fill="#166534">Data Nodes</text>
  <text x="1110" y="314" text-anchor="middle" font-size="8" fill="#4ade80">Cassandra, OpenSearch, PostgreSQL</text>
  <text x="1110" y="328" text-anchor="middle" font-size="8" fill="#4ade80">RabbitMQ, MinIO</text>
  <rect x="1000" y="450" width="220" height="40" rx="8" fill="#fef2f2" stroke="#fca5a5" stroke-width="1.3" filter="url(#${fid})"/>
  <text x="1110" y="468" text-anchor="middle" font-size="11" font-weight="700" fill="#991b1b">Mail Server</text>
  <text x="1110" y="482" text-anchor="middle" font-size="8" fill="#f87171">SMTP relay</text>

  <!-- RIGHT LINKS (per-port coloring) -->
  <g fill="none">
    <path d="M 896,220 H 930 a 4,4 0 0 1 4,4 V 284 a 4,4 0 0 0 4,4 H 1000" stroke="${c9042.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 896,270 H 946 a 4,4 0 0 1 4,4 V 296 a 4,4 0 0 0 4,4 H 1000" stroke="${c9200.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 896,320 H 1000" stroke="${c5432.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 896,370 H 970 a 4,4 0 0 0 4,-4 V 340 a 4,4 0 0 1 4,-4 H 1000" stroke="${c5672.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 896,420 H 980 a 4,4 0 0 0 4,-4 V 346 a 4,4 0 0 1 4,-4 H 1000" stroke="${c9000.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 896,470 H 1000" stroke="${c587.link}" stroke-width="1.3" opacity="0.6"/>
  </g>

  <!-- Legend -->
  ${render_legend(700, 820)}

</svg>`
}
