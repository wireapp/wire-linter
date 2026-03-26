/**
 * Checks if ports between cluster nodes actually work.
 *
 * Looks at the network/{hostname}/port_connectivity target to see if
 * data can flow between kubenodes and datanodes on all the ports that matter.
 * If everything's open, we're good. Some blocked: warning. Critical ports dead: bad.
 *
 * Regex pattern finds all the per-host results.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class PortConnectivityChecker extends BaseChecker {
    readonly path: string = 'network/.*/port_connectivity'
    readonly name: string = 'Inter-node port connectivity'
    readonly category: string = 'Networking / Ports'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Verifies that data can flow between cluster nodes (**kubenodes** and **datanodes**) on all required internal ports. Blocked inter-node ports cause silent failures in database replication, service discovery, and internal API calls.'

    check(data: DataLookup): CheckResult {
        // Grab all the per-host connectivity results
        const matches = data.find(/^network\/.*\/port_connectivity$/)

        // No data means the gatherer never ran this check
        if (matches.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'Port connectivity data was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has SSH access to all cluster nodes\n2. Re-run the gatherer with the `port_connectivity` target enabled\n3. Check gatherer logs for connection errors or timeouts',
                recommendation: 'Port connectivity wasn\'t tested. Run the gatherer with port_connectivity to see which inter-node ports actually work.',
            }
        }

        // Extract the "15/18 open" counts from each host
        let total_open = 0
        let total_tested = 0
        const problem_hosts: string[] = []

        for (const dp of matches) {
            const val = String(dp.value ?? '')
            const match = val.match(/^(\d+)\/(\d+)\s+open$/)

            if (match && match[1] && match[2]) {
                const open = parseInt(match[1], 10)
                const tested = parseInt(match[2], 10)
                total_open += open
                total_tested += tested

                // Keep a list of hosts with blocked ports
                if (open < tested) {
                    const host_name = dp.metadata?.host_name as string | undefined
                    problem_hosts.push(host_name ?? dp.path)
                }
            }
        }

        // Couldn't parse anything useful
        if (total_tested === 0) {
            return {
                status: 'warning',
                status_reason: 'Port connectivity data was returned but could not be parsed into open/tested counts.',
                fix_hint: '1. Check that the gatherer target is producing output in the expected `N/M open` format\n2. Review raw gatherer output for errors or unexpected formats\n3. Re-run the gatherer and inspect the JSONL output for `port_connectivity` entries',
                recommendation: 'Got port connectivity data but couldn\'t make sense of it.',
            }
        }

        // Everything's open, we're good
        if (total_open === total_tested) {
            return {
                status: 'healthy',
                status_reason: 'All **{{total_tested}}** tested inter-node ports are open.',
                display_value: `${total_open}/${total_tested} open`,
                template_data: { total_tested },
            }
        }

        // Some ports are blocked
        const blocked = total_tested - total_open
        return {
            status: 'unhealthy',
            status_reason: '**{{blocked}}** of **{{total_tested}}** inter-node ports are blocked on {{host_count}} host(s): {{problem_hosts}}.',
            fix_hint: '1. Test connectivity from the source node: `nc -zv <target_host> <port>`\n2. Check firewall rules on each problem host: `iptables -L -n` or `ufw status`\n3. Verify the service is listening: `ss -tlnp | grep <port>`\n4. Check cloud provider security groups and network ACLs if applicable\n5. Review the **Ports** tab for a detailed breakdown of which ports are blocked on which hosts',
            display_value: `${total_open}/${total_tested} open`,
            recommendation: `${blocked} port(s) blocked. Check these hosts: ${problem_hosts.join(', ')}. See the Ports tab for details and fixes.`,
            template_data: {
                blocked,
                total_tested,
                host_count: problem_hosts.length,
                problem_hosts: problem_hosts.join(', '),
            },
        }
    }
}

export default PortConnectivityChecker
