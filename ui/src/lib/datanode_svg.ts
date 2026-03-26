// Renders the data node architecture diagram as SVG
// Shows Cassandra, RabbitMQ, PostgreSQL, OpenSearch, MinIO with incoming ports (left)
// and replication ports (right). Colors: green=open, red=closed, yellow=filtered, gray=untested

// Ours
import { colors_for_status, esc, render_legend, render_shadow_filter } from './svg_helpers'

// node_name: "datanode-10.0.0.5", node_ip: the IP
// incoming_status, outgoing_status: port -> status maps
// id_suffix: unique suffix for filter IDs
export function render_datanode_svg(
    node_name: string,
    node_ip: string,
    incoming_status: Map<number, string>,
    outgoing_status: Map<number, string>,
    id_suffix: string,
): string {
    // Incoming ports from kubenodes
    const ci9042 = colors_for_status(incoming_status.get(9042))
    const ci5672 = colors_for_status(incoming_status.get(5672))
    const ci5432 = colors_for_status(incoming_status.get(5432))
    const ci9200 = colors_for_status(incoming_status.get(9200))
    const ci9000 = colors_for_status(incoming_status.get(9000))
    const ci443  = colors_for_status(incoming_status.get(443))

    // Outgoing ports to other datanodes
    const co7000 = colors_for_status(outgoing_status.get(7000))
    const co9300 = colors_for_status(outgoing_status.get(9300))
    const co9000 = colors_for_status(outgoing_status.get(9000))

    const fid = `sh_${id_suffix}`

    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 595" font-family="Inter, 'Segoe UI', system-ui, sans-serif" font-size="11">
  ${render_shadow_filter(fid)}

  <rect width="1400" height="595" fill="#f8fafc" rx="6"/>
  <text x="700" y="26" text-anchor="middle" font-size="16" font-weight="700" fill="#0f172a">${esc(node_name)} (${esc(node_ip)})</text>

  <!-- Data node container -->
  <rect x="430" y="42" width="540" height="490" rx="14" fill="white" stroke="#94a3b8" stroke-width="1.8" filter="url(#${fid})"/>
  <text x="700" y="66" text-anchor="middle" font-size="13" font-weight="700" fill="#334155">${esc(node_name)}</text>
  <line x1="450" y1="74" x2="950" y2="74" stroke="#e2e8f0"/>

  <!-- STORAGE section background -->
  <rect x="548" y="78" width="314" height="362" rx="6" fill="#fffef7" stroke="#fde68a" stroke-width="0.6"/>
  <text x="556" y="90" font-size="7" font-weight="600" fill="#d97706" letter-spacing="0.5" opacity="0.7">STORAGE</text>

  <!-- Cassandra -->
  <rect x="555" y="84" width="300" height="64" rx="8" fill="#fffbeb" stroke="#fcd34d" stroke-width="1.3"/>
  <text x="705" y="106" text-anchor="middle" font-size="12" font-weight="700" fill="#78350f">Cassandra</text>
  <text x="705" y="120" text-anchor="middle" font-size="8.5" fill="#b45309">high-performance data store</text>
  <text x="705" y="134" text-anchor="middle" font-size="8" fill="#d97706">accounts, auth, conversations, SSO</text>

  <!-- RabbitMQ -->
  <rect x="555" y="160" width="300" height="58" rx="8" fill="#fffbeb" stroke="#fcd34d" stroke-width="1.3"/>
  <text x="705" y="182" text-anchor="middle" font-size="12" font-weight="700" fill="#78350f">RabbitMQ</text>
  <text x="705" y="198" text-anchor="middle" font-size="8.5" fill="#b45309">message broker</text>
  <text x="705" y="210" text-anchor="middle" font-size="8" fill="#d97706">async jobs, federation</text>

  <!-- PostgreSQL -->
  <rect x="555" y="230" width="300" height="58" rx="8" fill="#fffbeb" stroke="#fcd34d" stroke-width="1.3"/>
  <text x="705" y="252" text-anchor="middle" font-size="12" font-weight="700" fill="#78350f">PostgreSQL</text>
  <text x="705" y="268" text-anchor="middle" font-size="8.5" fill="#b45309">relational store</text>
  <text x="705" y="280" text-anchor="middle" font-size="8" fill="#d97706">conversations, teams metadata</text>

  <!-- OpenSearch -->
  <rect x="555" y="300" width="300" height="58" rx="8" fill="#fffbeb" stroke="#fcd34d" stroke-width="1.3"/>
  <text x="705" y="322" text-anchor="middle" font-size="12" font-weight="700" fill="#78350f">OpenSearch</text>
  <text x="705" y="338" text-anchor="middle" font-size="8.5" fill="#b45309">user search index</text>
  <text x="705" y="350" text-anchor="middle" font-size="8" fill="#d97706">data mirrored from Cassandra</text>

  <!-- MinIO / S3 -->
  <rect x="555" y="370" width="300" height="64" rx="8" fill="#fffbeb" stroke="#fcd34d" stroke-width="1.3"/>
  <text x="705" y="392" text-anchor="middle" font-size="12" font-weight="700" fill="#78350f">MinIO / S3</text>
  <text x="705" y="408" text-anchor="middle" font-size="8.5" fill="#b45309">S3-compatible object storage</text>
  <text x="705" y="422" text-anchor="middle" font-size="8" fill="#d97706">encrypted assets</text>

  <!-- Incoming port pills -->
  <g font-size="9" font-weight="600" font-family="'JetBrains Mono', 'Fira Code', monospace">
    <rect x="394" y="105" width="72" height="22" rx="11" fill="white" stroke="${ci9042.stroke}" stroke-width="1.4"/>
    <text x="416" y="120" fill="${ci9042.text}">&#9654; 9042</text>
    <rect x="394" y="178" width="72" height="22" rx="11" fill="white" stroke="${ci5672.stroke}" stroke-width="1.4"/>
    <text x="416" y="193" fill="${ci5672.text}">&#9654; 5672</text>
    <rect x="394" y="248" width="72" height="22" rx="11" fill="white" stroke="${ci5432.stroke}" stroke-width="1.4"/>
    <text x="416" y="263" fill="${ci5432.text}">&#9654; 5432</text>
    <rect x="394" y="318" width="72" height="22" rx="11" fill="white" stroke="${ci9200.stroke}" stroke-width="1.4"/>
    <text x="416" y="333" fill="${ci9200.text}">&#9654; 9200</text>
    <rect x="394" y="391" width="72" height="22" rx="11" fill="white" stroke="${ci9000.stroke}" stroke-width="1.4"/>
    <text x="416" y="406" fill="${ci9000.text}">&#9654; 9000</text>
    <rect x="394" y="441" width="72" height="22" rx="11" fill="white" stroke="${ci443.stroke}" stroke-width="1.4"/>
    <text x="420" y="456" fill="${ci443.text}">&#9654; 443</text>
  </g>

  <!-- Outgoing port pills -->
  <g font-size="9" font-weight="600" font-family="'JetBrains Mono', 'Fira Code', monospace">
    <rect x="934" y="105" width="72" height="22" rx="11" fill="white" stroke="${co7000.stroke}" stroke-width="1.4"/>
    <text x="948" y="120" fill="${co7000.text}">7000 &#9654;</text>
    <rect x="934" y="318" width="72" height="22" rx="11" fill="white" stroke="${co9300.stroke}" stroke-width="1.4"/>
    <text x="948" y="333" fill="${co9300.text}">9300 &#9654;</text>
    <rect x="934" y="391" width="72" height="22" rx="11" fill="white" stroke="${co9000.stroke}" stroke-width="1.4"/>
    <text x="948" y="406" fill="${co9000.text}">9000 &#9654;</text>
  </g>

  <!-- Lines from databases to port pills -->
  <g fill="none">
    <line x1="466" y1="116" x2="555" y2="116" stroke="${ci9042.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="855" y1="116" x2="934" y2="116" stroke="${co7000.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="466" y1="189" x2="555" y2="189" stroke="${ci5672.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="466" y1="259" x2="555" y2="259" stroke="${ci5432.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="466" y1="329" x2="555" y2="329" stroke="${ci9200.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="855" y1="329" x2="934" y2="329" stroke="${co9300.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="466" y1="402" x2="555" y2="402" stroke="${ci9000.link}" stroke-width="1.3" opacity="0.55"/>
    <path d="M 555,422 H 480 a 4,4 0 0 0 -4,4 V 448 a 4,4 0 0 1 -4,4 H 466" stroke="${ci443.link}" stroke-width="1.3" opacity="0.55"/>
    <line x1="855" y1="402" x2="934" y2="402" stroke="${co9000.link}" stroke-width="1.3" opacity="0.55"/>
  </g>

  <!-- Kubenode services -->
  <rect x="30" y="82" width="220" height="32" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="98" font-size="10" font-weight="600" fill="#1e40af">gundeck</text>
  <text x="104" y="98" font-size="8" fill="#60a5fa">push &amp; delivery</text>
  <rect x="30" y="122" width="220" height="32" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="138" font-size="10" font-weight="600" fill="#1e40af">spar</text>
  <text x="68" y="138" font-size="8" fill="#60a5fa">SSO &amp; SCIM</text>
  <rect x="30" y="174" width="220" height="32" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="190" font-size="10" font-weight="600" fill="#1e40af">background-worker</text>
  <rect x="30" y="246" width="220" height="32" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="262" font-size="10" font-weight="600" fill="#1e40af">galley</text>
  <text x="82" y="262" font-size="8" fill="#60a5fa">conversations</text>
  <rect x="30" y="318" width="220" height="32" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="334" font-size="10" font-weight="600" fill="#1e40af">brig</text>
  <text x="68" y="334" font-size="8" fill="#60a5fa">auth &amp; accounts</text>
  <rect x="30" y="390" width="220" height="32" rx="6" fill="#dbeafe" stroke="#93c5fd" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="406" font-size="10" font-weight="600" fill="#1e40af">cargohold</text>
  <text x="114" y="406" font-size="8" fill="#60a5fa">assets</text>
  <rect x="30" y="438" width="220" height="28" rx="6" fill="#e0f2fe" stroke="#7dd3fc" stroke-width="1.2" filter="url(#${fid})"/>
  <text x="44" y="455" font-size="10" font-weight="600" fill="#0369a1">External Clients</text>

  <!-- Links to kubenode services, colored by port -->
  <g fill="none">
    <path d="M 250,189 H 394" stroke="${ci5672.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,259 H 394" stroke="${ci5432.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,329 H 394" stroke="${ci9200.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,402 H 394" stroke="${ci9000.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,452 H 394" stroke="${ci443.link}" stroke-width="1.3" opacity="0.6" stroke-dasharray="4,2"/>
    <path d="M 250,98  H 376 a 4,4 0 0 1 4,4  V 112 a 4,4 0 0 0 4,4  H 394" stroke="${ci9042.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,138 H 348 a 4,4 0 0 0 4,-4 V 122 a 4,4 0 0 1 4,-4 H 394" stroke="${ci9042.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,196 H 312 a 4,4 0 0 0 4,-4 V 124 a 4,4 0 0 1 4,-4 H 394" stroke="${ci9042.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,252 H 288 a 4,4 0 0 0 4,-4 V 126 a 4,4 0 0 1 4,-4 H 394" stroke="${ci9042.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,322 H 270 a 4,4 0 0 0 4,-4 V 128 a 4,4 0 0 1 4,-4 H 394" stroke="${ci9042.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,268 H 296 a 4,4 0 0 0 4,-4 V 189 a 4,4 0 0 1 4,-4 H 394" stroke="${ci5672.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,338 H 278 a 4,4 0 0 0 4,-4 V 196 a 4,4 0 0 1 4,-4 H 394" stroke="${ci5672.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 250,344 H 336 a 4,4 0 0 0 4,-4 V 259 a 4,4 0 0 1 4,-4 H 394" stroke="${ci5432.link}" stroke-width="1.3" opacity="0.6"/>
  </g>

  <!-- Other data nodes -->
  <rect x="1100" y="210" width="220" height="84" rx="8" fill="#f0fdf4" stroke="#86efac" stroke-width="1.3" filter="url(#${fid})"/>
  <text x="1210" y="236" text-anchor="middle" font-size="11" font-weight="700" fill="#166534">Other Data Nodes</text>
  <text x="1210" y="254" text-anchor="middle" font-size="9" fill="#4ade80">Cassandra + OpenSearch + MinIO</text>
  <text x="1210" y="270" text-anchor="middle" font-size="8" fill="#86efac">replication peers</text>

  <!-- Links to other data nodes, colored by port -->
  <g fill="none">
    <path d="M 1006,116 H 1030 a 4,4 0 0 1 4,4 V 226 a 4,4 0 0 0 4,4 H 1100" stroke="${co7000.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 1006,329 H 1058 a 4,4 0 0 0 4,-4 V 256 a 4,4 0 0 1 4,-4 H 1100" stroke="${co9300.link}" stroke-width="1.3" opacity="0.6"/>
    <path d="M 1006,402 H 1074 a 4,4 0 0 0 4,-4 V 278 a 4,4 0 0 1 4,-4 H 1100" stroke="${co9000.link}" stroke-width="1.3" opacity="0.6"/>
  </g>

  <!-- Legend -->
  ${render_legend(700, 580)}

</svg>`
}
