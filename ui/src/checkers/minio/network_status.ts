/**
 * Checks if MinIO's network is healthy across all nodes.
 *
 * Uses databases/minio/network_status (something like «6/6 OK»). If there's
 * no «OK» in there, nodes can't talk to each other.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class NetworkStatusChecker extends BaseChecker {
    readonly path: string = 'minio/network_status'
    readonly name: string = 'Network status'
    readonly category: string = 'Data / MinIO'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Verifies that all **MinIO nodes** can communicate with each other over the network. Broken inter-node connectivity prevents **data replication** and can make stored files inaccessible.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/minio/network_status')

        // Couldn't get network status
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'MinIO network status data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the MinIO host\n2. Check that `mc admin info` runs successfully against the MinIO endpoint\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'No network status data yet.',
            }
        }

        const val: string = String(point.value)

        // No «OK» in the result means nodes aren't talking properly
        if (!val.includes('OK')) {
            return {
                status: 'unhealthy',
                status_reason: 'MinIO network status is **{{status_value}}** — nodes are not communicating properly.',
                fix_hint: '1. Check MinIO cluster info: `mc admin info <alias>`\n2. Verify network connectivity between MinIO nodes: `ping <node_ip>`\n3. Check MinIO service logs: `journalctl -u minio` or `kubectl logs <minio_pod>`\n4. Ensure firewall rules allow traffic on MinIO ports (default `9000`)\n5. Run a heal operation to repair any inconsistencies: `mc admin heal -r <alias>`',
                recommendation: 'MinIO nodes have network issues. Run mc admin info to dig deeper.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { status_value: val },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All MinIO nodes report **OK** network status ({{status_value}}).',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { status_value: val },
        }
    }
}

export default NetworkStatusChecker
