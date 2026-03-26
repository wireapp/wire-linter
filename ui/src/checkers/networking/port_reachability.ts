/**
 * Checks if the right ports are reachable from the outside.
 *
 * Looks at network/port_reachability (boolean or string).
 * Wire needs 443 TCP, 80 TCP, 3478 TCP+UDP, and 32768-65535 UDP.
 * If they're blocked, things just... don't work, no obvious error.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class PortReachabilityChecker extends BaseChecker {
    readonly path: string = 'networking/port_reachability'
    readonly data_path: string = 'network/port_reachability'
    readonly name: string = 'Essential ports reachable from outside'
    readonly category: string = 'Networking / Calling'
    readonly interest = 'Health, Setup' as const

    readonly requires_external_access: boolean = true
    readonly explanation: string = 'Verifies that essential ports (`443` TCP, `80` TCP, `3478` TCP+UDP, `32768-65535` UDP) are reachable from outside the cluster. Blocked ports silently prevent clients from connecting, making calls, or loading the Wire webapp.'

    check(data: DataLookup): CheckResult {
        // Check before get() so the sentinel doesn't pollute the accessed points list
        if (data.is_not_applicable('network/port_reachability')) {
            return {
                status: 'not_applicable',
                status_reason: 'Gatherer ran from inside the cluster; external port reachability cannot be tested from there.',
                recommendation: 'This needs to run from outside. Use --source external to test from the internet.',
            }
        }

        const point = data.get('network/port_reachability')

        // Target was not collected or not applicable for this run
        if (!point) {
            // Gatherer was on the admin host, can't test from outside
            if (data.is_not_applicable('network/port_reachability')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'Gatherer ran from inside the cluster; external port reachability cannot be tested from there.',
                    recommendation: 'This needs to run from outside. Use --source external to test from the internet.',
                }
            }

            return {
                status: 'gather_failure',
                status_reason: 'Port reachability data was not collected.',
                fix_hint: '1. Re-run the gatherer with the `port_reachability` target enabled\n2. Ensure the gatherer runs from **outside** the cluster (use `--source external`)\n3. Check gatherer logs for connection errors or timeouts',
                recommendation: 'Port reachability check wasn\'t run.',
            }
        }

        // Data point exists but the command failed, so value is null
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Port reachability data was collected but the value is null, indicating the gathering command failed.',
                recommendation: 'Re-run the gatherer to collect port reachability data.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean

        // Include the domain in the recommendation so the operator knows
        // which host to check firewall rules for
        const domain: string = data.config?.cluster.domain ?? ''
        const target_hint: string = domain ? ` on \`${domain}\`` : ''

        // String result if there's text, ports work
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'All essential ports are reachable from outside{{target_hint}}.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { target_hint, domain },
                }
            }

            // Empty string means blocked
            return {
                status: 'unhealthy',
                status_reason: 'Essential ports are **not reachable** from outside{{target_hint}}.',
                fix_hint: '1. Test port connectivity: `nc -zv {{domain}} 443` and `nc -zv {{domain}} 80`\n2. Test TURN port: `nc -zvu {{domain}} 3478`\n3. Check firewall rules: `iptables -L -n` or cloud provider security groups\n4. Verify the services are listening: `ss -tlnp | grep -E \"(443|80|3478)\"`\n5. Check cloud provider security groups and network ACLs for ports `443`, `80`, `3478`, and UDP range `32768-65535`',
                recommendation: `Not all essential ports are reachable${domain ? ` on ${domain}` : ''} (443 TCP, 80 TCP, 3478 TCP+UDP, 32768-65535 UDP). Blocked ports break calls and other features silently.`,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { target_hint, domain },
            }
        }

        // Boolean true is good
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'All essential ports are reachable from outside{{target_hint}}.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { target_hint, domain },
            }
        }

        // Boolean false means something's blocked
        return {
            status: 'unhealthy',
            status_reason: 'Essential ports are **not reachable** from outside{{target_hint}}.',
            fix_hint: '1. Test port connectivity: `nc -zv {{domain}} 443` and `nc -zv {{domain}} 80`\n2. Test TURN port: `nc -zvu {{domain}} 3478`\n3. Check firewall rules: `iptables -L -n` or cloud provider security groups\n4. Verify the services are listening: `ss -tlnp | grep -E \"(443|80|3478)\"`\n5. Check cloud provider security groups and network ACLs for ports `443`, `80`, `3478`, and UDP range `32768-65535`',
            recommendation: `Not all essential ports are reachable${domain ? ` on ${domain}` : ''} (443 TCP, 80 TCP, 3478 TCP+UDP, 32768-65535 UDP). Blocked ports break calls and other features silently.`,
            display_value: val,
            raw_output: point.raw_output,
            template_data: { target_hint, domain },
        }
    }
}

export default PortReachabilityChecker
