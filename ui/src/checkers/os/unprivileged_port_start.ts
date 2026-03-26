/**
 * Checks net.ipv4.ip_unprivileged_port_start across kubenodes.
 *
 * Consumes all os/<node>/unprivileged_port_start targets (int per node).
 * If the value's above 443, rootless containers can't bind to that port.
 * Containers with NET_BIND_SERVICE (like ingress-nginx) can bypass this.
 * See JCT-34.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

// Wire requires binding to port 443 the sysctl value must be at or below this
const WIRE_MIN_PORT = 443

export class UnprivilegedPortStartChecker extends BaseChecker {
    readonly path: string = 'os/unprivileged_port_start'
    readonly name: string = 'net.ipv4.ip_unprivileged_port_start on kubenodes (see: JCT-34)'
    readonly category: string = 'OS / System'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Checks the `net.ipv4.ip_unprivileged_port_start` sysctl on each kubenode. If set above **443**, rootless containers without `NET_BIND_SERVICE` cannot bind to port 443, preventing ingress from serving HTTPS traffic.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        // Find one data point per kubenode path is os/<nodename>/unprivileged_port_start
        // Use find_applicable to exclude sentinel points (value=null) emitted when SSH is disabled
        const points = data.find_applicable(/^os\/.*\/unprivileged_port_start$/)

        // Nothing collected from any node
        if (points.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'Could not retrieve `net.ipv4.ip_unprivileged_port_start` data from any kubenode.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to all kubenodes and can run `sysctl net.ipv4.ip_unprivileged_port_start`. Verify that node hostnames in the inventory are correct.',
                recommendation: 'net.ipv4.ip_unprivileged_port_start data not collected from any kubenode.',
            }
        }

        // Find nodes where the value is too high, using parse_number to handle
        // string-encoded integers emitted by the Python gatherer (e.g. {"value": "1024"})
        const failing_nodes: string[] = points
            .filter((point) => {
                const value = parse_number(point)
                return value !== null && value > WIRE_MIN_PORT
            })
            .map((point) => {
                // Node name is the second part of the path: os/<nodename>/unprivileged_port_start
                const node_name = point.path.split('/')[1] ?? 'unknown'
                const value = parse_number(point) as number
                return `${node_name} (=${value})`
            })

        const combined_raw = points
            .map((point) => point.raw_output)
            .filter(Boolean)
            .join('\n---\n')

        if (failing_nodes.length > 0) {
            const node_list = failing_nodes.join(', ')

            return {
                status: 'warning',
                status_reason: '**{{count}}** kubenode{{count_suffix}} `net.ipv4.ip_unprivileged_port_start` set above **{{min_port}}**: {{node_list}}.',
                fix_hint: '1. On each affected node, set the sysctl value:\n   ```\n   sysctl -w net.ipv4.ip_unprivileged_port_start={{min_port}}\n   ```\n2. Make it persistent across reboots:\n   ```\n   echo \'net.ipv4.ip_unprivileged_port_start={{min_port}}\' > /etc/sysctl.d/99-wire-unprivileged-ports.conf\n   ```\n\n**Note:** `ingress-nginx` has `NET_BIND_SERVICE` and is not affected, but other rootless containers that need port 443 will fail to bind.',
                recommendation: [
                    `net.ipv4.ip_unprivileged_port_start > ${WIRE_MIN_PORT} on: ${node_list}.`,
                    '',
                    'Containers without NET_BIND_SERVICE can\'t bind to port 443.',
                    'ingress-nginx has NET_BIND_SERVICE so it\'s not affected.',
                    'This matters for rootless containers that don\'t have the capability.',
                    '',
                    'If pods fail to bind port 443, run:',
                    `<command>sysctl -w net.ipv4.ip_unprivileged_port_start=${WIRE_MIN_PORT}</command>`,
                    `<command>echo 'net.ipv4.ip_unprivileged_port_start=${WIRE_MIN_PORT}' > /etc/sysctl.d/99-wire-unprivileged-ports.conf</command>`,
                ].join('\n'),
                display_value: `${failing_nodes.length} node(s) above ${WIRE_MIN_PORT}`,
                raw_output: combined_raw,
                template_data: { count: failing_nodes.length, count_suffix: failing_nodes.length === 1 ? ' has' : 's have', min_port: WIRE_MIN_PORT, node_list },
            }
        }

        // All configured correctly — parse_number handles both numeric and string-encoded values
        const max_value = Math.max(
            ...points.map((p) => parse_number(p) ?? 0)
        )

        return {
            status: 'healthy',
            status_reason: 'All kubenodes have `net.ipv4.ip_unprivileged_port_start` at or below **{{min_port}}** (highest: **{{max_value}}**).',
            display_value: max_value,
            raw_output: combined_raw,
            template_data: { min_port: WIRE_MIN_PORT, max_value },
        }
    }
}

export default UnprivilegedPortStartChecker
