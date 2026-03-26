/**
 * Makes sure the Redis pod is actually running.
 *
 * Reads the databases/redis/status target (string like "running").
 * If it's not "running", Redis is down and session caching and real-time features break.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class PodStatusChecker extends BaseChecker {
    readonly path: string = 'redis/pod_status'
    readonly data_path: string = 'databases/redis/status'
    readonly name: string = 'Pod running status'
    readonly category: string = 'Data / Redis'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Confirms the **Redis pod** is running. When Redis is down, **session caching**, **presence tracking**, and other real-time Wire features stop working.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/redis/status')

        // No data from the backend
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Redis pod status data was not collected.',
                fix_hint: '1. Verify the Redis pod exists: `kubectl get pods -l app=redis`\n2. Check pod events: `kubectl describe pod <redis_pod>`\n3. Verify the gatherer can reach the Kubernetes API\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Pod running status data not collected.',
            }
        }

        // Underlying command failed — value is null/undefined
        if (point.value === null || point.value === undefined) {
            return {
                status: 'gather_failure',
                status_reason: point.metadata?.error ?? 'Redis pod status value is missing.',
                recommendation: 'The gatherer collected this data point but the underlying command failed. Check Redis accessibility.',
                raw_output: point.raw_output,
            }
        }

        const val: string = point.value as string

        // Not "running" means Redis is down
        if (val !== 'running') {
            return {
                status: 'unhealthy',
                status_reason: 'Redis pod status is **{{pod_status}}** instead of the expected **running**.',
                fix_hint: '1. Check pod status: `kubectl get pods -l app=redis`\n2. Inspect pod events: `kubectl describe pod <redis_pod>`\n3. Check pod logs: `kubectl logs <redis_pod>`\n4. If the pod is in `CrashLoopBackOff`, check for configuration errors or resource limits\n5. Try restarting the pod: `kubectl delete pod <redis_pod>` (the StatefulSet/Deployment will recreate it)\n6. Verify Redis connectivity: `kubectl exec <redis_pod> -- redis-cli ping`',
                recommendation: 'Redis is down. Session caching and real-time features are broken.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { pod_status: val },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Redis pod is **running**.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default PodStatusChecker
