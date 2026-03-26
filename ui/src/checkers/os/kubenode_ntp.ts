/**
 * Checks NTP synchronization on all kubenodes.
 *
 * Consumes all os/<node>/kubenode_ntp targets (boolean per node). Even small
 * clock drift breaks certificate validation and mangles log timestamps. Any
 * desynchronized node is unhealthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class KubenodeNtpChecker extends BaseChecker {
    readonly path: string = 'os/kubenode_ntp'
    readonly name: string = 'NTP sync on kubenodes'
    readonly category: string = 'OS / System'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies **NTP synchronization** across all Kubernetes nodes. Even small clock drift between nodes breaks certificate validation, corrupts log ordering, and causes **token expiration mismatches**.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const points = data.find_applicable(/^os\/.*\/kubenode_ntp$/)

        // No NTP data collected
        if (points.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'NTP synchronization data was not collected from any kubenode.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to all kubenodes and can run `timedatectl`. Verify that node hostnames in the inventory match the actual nodes.',
                recommendation: 'NTP sync on kubenodes data not collected.',
            }
        }

        // Extract node name from path (e.g., "os/kubenode1/kubenode_ntp" -> "kubenode1")
        const unsynchronized: string[] = points
            .filter((point) => coerce_boolean(point.value) !== true)
            .map((point) => point.path.split('/')[1] ?? 'unknown')

        // Aggregate raw output from all consumed targets
        const combined_raw: string = points
            .map((point) => point.raw_output)
            .filter(Boolean)
            .join('\n---\n')

        // Any desynchronized node breaks certs and logs
        if (unsynchronized.length > 0) {
            const node_list = unsynchronized.join(', ')

            return {
                status: 'unhealthy',
                status_reason: '**{{count}}** kubenode{{count_suffix}} not NTP-synchronized: {{node_list}}.',
                fix_hint: '1. SSH into each affected node and check the NTP service:\n   ```\n   systemctl status chronyd || systemctl status ntp\n   ```\n2. If not installed, install chrony: `apt install chrony`\n3. Start and enable: `systemctl enable --now chronyd`\n4. Force sync: `chronyc makestep`\n5. Verify: `timedatectl | grep "synchronized"`\n\nAffected nodes: {{node_list}}',
                recommendation: `NTP not synchronized on kubenode(s): ${node_list}. Clock drift breaks certificate validation and log timestamps.`,
                display_value: `${node_list} not synchronized`,
                raw_output: combined_raw,
                template_data: { count: unsynchronized.length, count_suffix: unsynchronized.length === 1 ? ' is' : 's are', node_list },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All **{{total}}** kubenode{{total_suffix}} NTP-synchronized.',
            display_value: 'all synchronized',
            raw_output: combined_raw,
            template_data: { total: points.length, total_suffix: points.length === 1 ? ' is' : 's are' },
        }
    }
}

export default KubenodeNtpChecker
