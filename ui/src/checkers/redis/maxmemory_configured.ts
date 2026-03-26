/**
 * Makes sure Redis has a maxmemory limit set.
 *
 * Reads the databases/redis/memory target (string with « max=... » format).
 * No limit means Redis balloons until the container or node runs out of RAM and gets nuked.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class MaxmemoryConfiguredChecker extends BaseChecker {
    readonly path: string = 'redis/maxmemory_configured'
    readonly data_path: string = 'databases/redis/memory'
    readonly name: string = 'Maxmemory limit configured'
    readonly category: string = 'Data / Redis'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Ensures Redis has a `maxmemory` limit configured. Without a cap, Redis grows unbounded until it exhausts the container or node memory, causing an **OOM kill** that takes down caching and sessions.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/redis/memory')

        // Couldn't get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Redis memory configuration data was not collected.',
                fix_hint: '1. Verify the Redis pod is running: `kubectl get pods -l app=redis`\n2. Check that `redis-cli` can connect: `kubectl exec <redis_pod> -- redis-cli ping`\n3. Try fetching memory info directly: `kubectl exec <redis_pod> -- redis-cli info memory`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Redis memory data not collected.',
            }
        }

        const val: string = String(point.value)

        // Parse "max=..." from the string (e.g., "used=998.50K, max=0B, evicted=0")
        const max_match = val.match(/max=(\S+)/)

        if (!max_match) {
            // Can't find the max value, so we're stuck
            return {
                status: 'warning',
                status_reason: 'Could not parse a `max=` value from Redis memory data: **{{memory_data}}**.',
                fix_hint: '1. Check Redis memory info directly: `kubectl exec <redis_pod> -- redis-cli info memory`\n2. Look for the `maxmemory` field in the output\n3. Verify the gatherer is parsing the correct data format\n4. If the format is unexpected, check the Redis version: `kubectl exec <redis_pod> -- redis-cli info server`',
                recommendation: 'Could not determine Redis maxmemory setting from collected data.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { memory_data: val },
            }
        }

        const max_value: string = max_match[1] ?? ''

        // "0B" or "0" means unlimited growth, which is bad
        if (max_value === '0B' || max_value === '0' || max_value === '0b') {
            return {
                status: 'warning',
                status_reason: 'Redis `maxmemory` is set to **0** (unlimited) — no memory cap is in place.',
                fix_hint: '1. Set a maxmemory limit: `kubectl exec <redis_pod> -- redis-cli config set maxmemory <bytes>`\n   Example for 512MB: `redis-cli config set maxmemory 536870912`\n2. Set an eviction policy: `kubectl exec <redis_pod> -- redis-cli config set maxmemory-policy allkeys-lru`\n3. Make the change persistent by updating the Redis configuration in the Helm values or ConfigMap\n4. Verify the setting: `kubectl exec <redis_pod> -- redis-cli config get maxmemory`',
                recommendation: 'Redis has no maxmemory limit set. It\'ll grow forever until the container or node runs out of RAM. Set a limit and pick an eviction policy.',
                display_value: 'no limit (0)',
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Redis `maxmemory` is configured to **{{max_value}}**.',
            display_value: `limit: ${max_value}`,
            raw_output: point.raw_output,
            template_data: { max_value },
        }
    }
}

export default MaxmemoryConfiguredChecker
