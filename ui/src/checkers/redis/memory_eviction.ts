/**
 * Checks if Redis is evicting keys or running low on memory.
 *
 * Reads the databases/redis/memory target which comes in a few flavors:
 * boolean: true = memory is fine, false = evicting keys (bad)
 * string: has "evict" = bad, otherwise fine
 *
 * When Redis starts evicting, sessions and caches poof, users disconnect randomly, service degrades.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class MemoryEvictionChecker extends BaseChecker {
    readonly path: string = 'redis/memory_eviction'
    readonly data_path: string = 'databases/redis/memory'
    readonly name: string = 'Memory usage and eviction status'
    readonly category: string = 'Data / Redis'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Monitors whether Redis is **evicting keys** due to memory pressure. Active eviction causes sessions and cached data to disappear, leading to random user disconnects and **degraded Wire performance**.'

    check(data: DataLookup): CheckResult {
        const point = data.get('databases/redis/memory')

        // No data from the backend
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Redis memory and eviction data was not collected.',
                fix_hint: '1. Verify the Redis pod is running: `kubectl get pods -l app=redis`\n2. Check that `redis-cli` can connect: `kubectl exec <redis_pod> -- redis-cli ping`\n3. Try fetching memory info directly: `kubectl exec <redis_pod> -- redis-cli info memory`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Memory usage and eviction status data not collected.',
            }
        }

        // Null value means the gatherer failed to retrieve the data
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Redis memory and eviction data was collected but returned null.',
                recommendation: 'Memory usage and eviction status data not available.',
            }
        }

        const val: boolean | string | number = point.value as boolean | string | number

        // Boolean true is all good
        if (typeof val === 'boolean') {
            if (val) {
                return {
                    status: 'healthy',
                    status_reason: 'Redis reports **no key eviction** is occurring.',
                    display_value: 'no eviction',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'Redis is actively **evicting keys** due to memory pressure.',
                fix_hint: '1. Check memory usage: `kubectl exec <redis_pod> -- redis-cli info memory`\n2. Check eviction stats: `kubectl exec <redis_pod> -- redis-cli info stats | grep evicted`\n3. Increase `maxmemory`: `kubectl exec <redis_pod> -- redis-cli config set maxmemory <bytes>`\n4. Review eviction policy: `kubectl exec <redis_pod> -- redis-cli config get maxmemory-policy`\n5. Identify large keys: `kubectl exec <redis_pod> -- redis-cli --bigkeys`\n6. Consider scaling Redis or reducing cached data volume',
                recommendation: 'Redis is evicting keys. Sessions and caches vanish, random disconnects happen.',
                display_value: 'evicting keys',
                raw_output: point.raw_output,
            }
        }

        // String value, look for "evicted=N" format; bad only if N > 0
        if (typeof val === 'string') {
            // Pull out the evicted count from "evicted=N" style strings
            const eviction_match = val.match(/evicted=(\d+)/i)

            if (eviction_match) {
                const evicted_count: number = parseInt(eviction_match[1] ?? '0', 10)

                // Zero evictions is fine, "evicted=0" is not a red flag
                if (evicted_count > 0) {
                    return {
                        status: 'unhealthy',
                        status_reason: 'Redis has evicted **{{evicted_count}}** key(s) due to memory pressure.',
                        fix_hint: '1. Check memory usage: `kubectl exec <redis_pod> -- redis-cli info memory`\n2. Check eviction stats: `kubectl exec <redis_pod> -- redis-cli info stats | grep evicted`\n3. Increase `maxmemory`: `kubectl exec <redis_pod> -- redis-cli config set maxmemory <bytes>`\n4. Review eviction policy: `kubectl exec <redis_pod> -- redis-cli config get maxmemory-policy`\n5. Identify large keys: `kubectl exec <redis_pod> -- redis-cli --bigkeys`\n6. Consider scaling Redis or reducing cached data volume',
                        recommendation: 'Redis is evicting keys. Sessions and caches vanish, random disconnects happen.',
                        display_value: val,
                        raw_output: point.raw_output,
                        template_data: { evicted_count },
                    }
                }

                return {
                    status: 'healthy',
                    status_reason: 'Redis reports **0** evicted keys — no memory pressure.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // For non-"evicted=N" strings, just check if "evict" is in there
            if (val.toLowerCase().includes('evict')) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Redis memory data mentions eviction: **{{memory_value}}**.',
                    fix_hint: '1. Check memory usage: `kubectl exec <redis_pod> -- redis-cli info memory`\n2. Check eviction stats: `kubectl exec <redis_pod> -- redis-cli info stats | grep evicted`\n3. Increase `maxmemory`: `kubectl exec <redis_pod> -- redis-cli config set maxmemory <bytes>`\n4. Review eviction policy: `kubectl exec <redis_pod> -- redis-cli config get maxmemory-policy`\n5. Identify large keys: `kubectl exec <redis_pod> -- redis-cli --bigkeys`\n6. Consider scaling Redis or reducing cached data volume',
                    recommendation: 'Redis is evicting keys. Sessions and caches vanish, random disconnects happen.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { memory_value: val },
                }
            }

            return {
                status: 'healthy',
                status_reason: 'Redis memory status is **{{memory_value}}** with no signs of eviction.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { memory_value: val },
            }
        }

        // Numeric value, just show it as-is and call it good
        return {
            status: 'healthy',
            status_reason: 'Redis memory value is **{{memory_value}}** with no eviction indicators.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { memory_value: val },
        }
    }
}

export default MemoryEvictionChecker
