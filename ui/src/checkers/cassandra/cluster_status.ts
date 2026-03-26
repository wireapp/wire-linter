/**
 * Checks the Cassandra cluster status across all nodes.
 *
 * Consumes the databases/cassandra/cluster_status target (a string like "UN").
 * If you see anything other than "UN" (Up/Normal), it means at least one node
 * is down, leaving, joining, or moving. All of those hurt cluster health.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class ClusterStatusChecker extends BaseChecker {
    readonly path: string = 'cassandra/cluster_status'
    readonly name: string = 'Cluster status'
    readonly category: string = 'Data / Cassandra'
    readonly interest = 'Health, Setup' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Verifies the Cassandra cluster is healthy with all nodes in **Up/Normal** (`UN`) state. Unhealthy nodes cause data inconsistency, increased latency, and risk of failed writes for Wire conversations and user data.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/cassandra/cluster_status')

        // Couldn't get cluster status data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra cluster status data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the Cassandra nodes\n2. Check that `nodetool status` runs successfully on the target host\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Couldn\'t collect cluster status data.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Cassandra cluster status data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Cluster status target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        // Unexpected type — collector returned a number or boolean instead of a string
        if (typeof point.value !== 'string') {
            return {
                status: 'gather_failure',
                status_reason: `Cassandra cluster status has unexpected type «${typeof point.value}».`,
                recommendation: 'Cluster status target returned a non-string value; check the collector output.',
                raw_output: point.raw_output,
            }
        }

        const val: string = point.value

        // Anything other than UN means something's wrong with a node
        if (val !== 'UN') {
            return {
                status: 'unhealthy',
                status_reason: 'Cluster status is **{{cluster_status}}** instead of the expected **UN** (Up/Normal), indicating one or more nodes are down, leaving, joining, or moving.',
                fix_hint: '1. Check cluster status: `nodetool status`\n2. Look for nodes that are not **UN** (Up/Normal)\n3. If a node is **DN** (Down), check its logs: `journalctl -u cassandra`\n4. If a node is joining/leaving, wait for the operation to complete before taking action\n5. For a node stuck in a non-normal state, try `nodetool describecluster` for more details',
                recommendation: `Cluster status is «${val}», but it should be «UN» (Up/Normal). Run <command>nodetool status</command> to see what's going on.`,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { cluster_status: val },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All Cassandra nodes are in **Up/Normal** (`UN`) state.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default ClusterStatusChecker
