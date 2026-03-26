/**
 * Checks if the etcd cluster that backs Kubernetes is healthy.
 *
 * Uses the kubernetes/etcd/health target, which can be a string like
 * « healthy » or a boolean value. An unhealthy etcd is a big problem
 * because etcd is what Kubernetes uses to store all its state.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class EtcdHealthChecker extends BaseChecker {
    readonly path: string = 'kubernetes/etcd_health'
    readonly name: string = 'etcd cluster health'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Checks whether the **etcd cluster** backing Kubernetes is healthy. Etcd stores all cluster state, so an unhealthy etcd means Kubernetes cannot persist or coordinate any changes, effectively freezing the entire platform.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/etcd/health')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'etcd cluster health data was not collected.',
                fix_hint: '1. Ensure the gatherer has **SSH access** to a control-plane node.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/etcd/health\n   ```\n3. Manually check etcd health on the control-plane node:\n   ```\n   etcdctl endpoint health --cluster\n   ```',
                recommendation: 'etcd cluster health data not collected.',
            }
        }

        // Gatherer sets value to null when the command fails
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'etcd cluster health data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'etcd health target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const value: string | boolean = point.value as string | boolean
        const unhealthy_fix_hint: string =
            '1. Check etcd member status on the control-plane node:\n   ```\n   etcdctl endpoint status --cluster -w table\n   etcdctl endpoint health --cluster\n   ```\n2. Check etcd pod logs:\n   ```\n   kubectl logs -n kube-system etcd-<node-name>\n   ```\n3. Common causes:\n   - **Disk I/O** too slow for etcd (etcd requires fast storage, ideally SSD)\n   - **Network partitions** between etcd members\n   - **Disk full** on the etcd data directory\n4. Check disk usage: `df -h /var/lib/etcd`\n5. If etcd is completely down, refer to the Kubernetes documentation on etcd disaster recovery.'

        // Boolean value true is healthy, false is not
        if (typeof value === 'boolean') {
            if (!value) {
                return {
                    status: 'unhealthy',
                    status_reason: 'etcd cluster reported as **not healthy** (returned false).',
                    fix_hint: unhealthy_fix_hint,
                    recommendation: 'etcd cluster is not healthy. etcd is the backbone of Kubernetes, so if it goes down, everything breaks.',
                    display_value: value,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'healthy',
                status_reason: 'etcd cluster reported as **healthy** (returned true).',
                display_value: value,
                raw_output: point.raw_output,
            }
        }

        // String value only "healthy" is acceptable
        if (value.toLowerCase() !== 'healthy') {
            return {
                status: 'unhealthy',
                status_reason: 'etcd cluster reported as "{{value}}" instead of "healthy".',
                fix_hint: unhealthy_fix_hint,
                recommendation: 'etcd cluster is not healthy. etcd is the backbone of Kubernetes, so if it goes down, everything breaks.',
                display_value: value,
                raw_output: point.raw_output,
                template_data: { value },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'etcd cluster reported as **healthy**.',
            display_value: value,
            raw_output: point.raw_output,
        }
    }
}

export default EtcdHealthChecker
