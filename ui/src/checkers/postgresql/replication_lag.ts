/**
 * Checks PostgreSQL replication lag between primary and standbys.
 *
 * Consumes the databases/postgresql/replication_lag target can be:
 * boolean: true = no lag, false = unhealthy
 * number: bytes/seconds of lag (>0 = warning)
 * string: textual description with lag=HH:MM:SS.us entries
 *
 * Sub-second lag is normal for streaming replication. We flag anything
 * above 1 second as a warning, above 30 seconds as unhealthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// Lag below 1 second is healthy
const LAG_WARNING_THRESHOLD_SECONDS = 1.0

// Lag above 30 seconds means standbys are way behind
const LAG_UNHEALTHY_THRESHOLD_SECONDS = 30.0

/**
 * Parse PostgreSQL interval strings like HH:MM:SS or HH:MM:SS.microseconds to seconds.
 * Returns 0 if empty or can't parse.
 */
function parse_pg_interval_seconds(interval: string): number {
    if (!interval || interval === '?') return 0

    const parts: string[] = interval.trim().split(':')
    if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) return 0

    const hours: number = parseFloat(parts[0])
    const minutes: number = parseFloat(parts[1])
    const seconds: number = parseFloat(parts[2])

    if (isNaN(hours) || isNaN(minutes) || isNaN(seconds)) return 0

    return hours * 3600 + minutes * 60 + seconds
}

/**
 * Extract max lag from a summary looks like:
 * «datanode2: lag=00:00:00.003795, state=streaming; datanode3: lag=00:00:00.003394, state=streaming»
 *
 * Returns null when no lag= patterns are found, so callers can distinguish
 * "zero lag" from "unrecognized output".
 */
function extract_max_lag_seconds(summary: string): number | null {
    const lag_pattern: RegExp = /lag=([\d:.]+)/g
    let max_lag: number = 0
    let found: boolean = false
    let match: RegExpExecArray | null

    while ((match = lag_pattern.exec(summary)) !== null) {
        if (!match[1]) continue
        found = true
        const lag_seconds: number = parse_pg_interval_seconds(match[1])
        if (lag_seconds > max_lag) max_lag = lag_seconds
    }

    return found ? max_lag : null
}

export class ReplicationLagChecker extends BaseChecker {
    readonly path: string = 'postgresql/replication_lag'
    readonly name: string = 'Replication lag'
    readonly category: string = 'Data / PostgreSQL'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Measures replication lag between the PostgreSQL primary and its standbys. High lag means standbys hold stale data, so a failover would lose recent writes -- including Wire messages, user changes, and team updates.'

    check(data: DataLookup): CheckResult {
        // Get lag data
        const point = data.get('databases/postgresql/replication_lag')

        // No data collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL replication lag data was not collected.',
                fix_hint: '1. Verify SSH connectivity to the PostgreSQL nodes\n2. Check that the primary is reachable: `pg_isready -h <primary_host>`\n3. Try querying replication lag manually: `psql -c "SELECT client_addr, replay_lag FROM pg_stat_replication"`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Replication lag data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'PostgreSQL replication lag data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Replication lag target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: number | string | boolean = point.value

        // Boolean true means no lag detected
        if (typeof val === 'boolean') {
            if (val) {
                return {
                    status: 'healthy',
                    status_reason: 'No PostgreSQL replication lag detected between primary and standbys.',
                    display_value: 'no lag',
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'PostgreSQL replication lag detected (boolean false from collector); standbys have **stale data**.',
                fix_hint: '1. Check replication status on the primary: `psql -c "SELECT client_addr, state, sent_lsn, replay_lsn, replay_lag FROM pg_stat_replication"`\n2. Check standby recovery state: `psql -c "SELECT pg_is_in_recovery(), pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()"`\n3. Check for long-running queries blocking replay on standbys: `psql -c "SELECT pid, query, state FROM pg_stat_activity WHERE state != \'idle\'"`\n4. Review PostgreSQL logs: `journalctl -u postgresql`\n5. If standby is far behind, consider re-cloning: `repmgr standby clone --force -h <primary_host> -d repmgr`',
                recommendation: 'PostgreSQL replication lag detected. Standbys have stale data and failover would lose recent writes.',
                display_value: 'lag detected',
                raw_output: point.raw_output,
            }
        }

        // Numeric lag value check thresholds
        if (typeof val === 'number') {
            if (val > LAG_UNHEALTHY_THRESHOLD_SECONDS) {
                return {
                    status: 'unhealthy',
                    status_reason: 'PostgreSQL replication lag is **{{lag_seconds}}s**, exceeding the **{{unhealthy_threshold}}s** unhealthy threshold.',
                    fix_hint: '1. Identify lagging standbys: `psql -c "SELECT client_addr, state, replay_lag FROM pg_stat_replication"`\n2. Check for long-running queries blocking replay: `psql -c "SELECT pid, query, state FROM pg_stat_activity WHERE state != \'idle\'"` on standbys\n3. Check I/O performance on standbys: `iostat -x 1 5`\n4. Review PostgreSQL logs for replication errors: `journalctl -u postgresql`\n5. If standby is too far behind, re-clone it: `repmgr standby clone --force -h <primary_host> -d repmgr`',
                    recommendation: `PostgreSQL lag is ${val}s. Standbys have stale data, failover would lose writes.`,
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { lag_seconds: val, unhealthy_threshold: LAG_UNHEALTHY_THRESHOLD_SECONDS },
                }
            }

            if (val > LAG_WARNING_THRESHOLD_SECONDS) {
                return {
                    status: 'warning',
                    status_reason: 'PostgreSQL replication lag is **{{lag_seconds}}s**, exceeding the **{{warning_threshold}}s** warning threshold but below the **{{unhealthy_threshold}}s** unhealthy threshold.',
                    fix_hint: '1. Monitor lag trend: `psql -c "SELECT client_addr, replay_lag FROM pg_stat_replication"`\n2. Check for heavy write load on the primary: `psql -c "SELECT xact_commit, xact_rollback FROM pg_stat_database WHERE datname = current_database()"`\n3. Verify network latency between primary and standbys\n4. Check I/O performance on standbys: `iostat -x 1 5`',
                    recommendation: `PostgreSQL lag is ${val}s. Watch it.`,
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { lag_seconds: val, warning_threshold: LAG_WARNING_THRESHOLD_SECONDS, unhealthy_threshold: LAG_UNHEALTHY_THRESHOLD_SECONDS },
                }
            }

            return {
                status: 'healthy',
                status_reason: 'PostgreSQL replication lag is **{{lag_seconds}}s**, within the healthy threshold of **{{warning_threshold}}s**.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { lag_seconds: val, warning_threshold: LAG_WARNING_THRESHOLD_SECONDS },
            }
        }

        // String lag description — check for ambiguous or unhealthy patterns first
        const lower_val: string = val.toLowerCase()

        // "no replication lag" explicitly says lag is absent — healthy
        // Must check before the broader "no replication" match below
        if (lower_val.includes('no replication lag')) {
            return {
                status: 'healthy',
                status_reason: `Replication status indicates no lag: «${val}».`,
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // "no replication" without "lag" could mean HA is not configured (single-node PostgreSQL)
        if (lower_val.includes('no replication')) {
            return {
                status: 'warning',
                status_reason: `Replication status suggests replication may not be configured: «${val}».`,
                recommendation: 'Verify PostgreSQL high-availability is configured with at least one standby. A single-node setup has no failover capability.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // "no lag" without the "no replication" prefix — healthy
        if (lower_val.includes('no lag')) {
            return {
                status: 'healthy',
                status_reason: 'Replication status indicates no lag: **{{lag_description}}**.',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { lag_description: val },
            }
        }

        // Parse lag times from the summary and check thresholds
        const max_lag_seconds: number | null = extract_max_lag_seconds(val)

        // No lag= patterns found — unrecognized output (likely an error message)
        if (max_lag_seconds === null) {
            return {
                status: 'warning',
                status_reason: `Replication lag output could not be parsed — no recognizable lag data found: «${val}».`,
                recommendation: 'The replication lag collector returned an unrecognized response. Check PostgreSQL connectivity and verify the replication status query runs successfully.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        if (max_lag_seconds > LAG_UNHEALTHY_THRESHOLD_SECONDS) {
            return {
                status: 'unhealthy',
                status_reason: 'Maximum replication lag is **{{max_lag}}s**, exceeding the **{{unhealthy_threshold}}s** unhealthy threshold.',
                fix_hint: '1. Identify lagging standbys from the replication summary\n2. Check standby replay status: `psql -c "SELECT pg_is_in_recovery(), pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()"`\n3. Check for long-running queries blocking replay on standbys\n4. Review PostgreSQL logs: `journalctl -u postgresql`\n5. If standby is too far behind, re-clone it: `repmgr standby clone --force -h <primary_host> -d repmgr`',
                recommendation: `PostgreSQL lag is ${max_lag_seconds.toFixed(1)}s. Standbys have stale data, failover would lose writes.`,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { max_lag: max_lag_seconds.toFixed(1), unhealthy_threshold: LAG_UNHEALTHY_THRESHOLD_SECONDS },
            }
        }

        if (max_lag_seconds > LAG_WARNING_THRESHOLD_SECONDS) {
            return {
                status: 'warning',
                status_reason: 'Maximum replication lag is **{{max_lag}}s**, exceeding the **{{warning_threshold}}s** warning threshold but below the **{{unhealthy_threshold}}s** unhealthy threshold.',
                fix_hint: '1. Monitor lag trend on the primary: `psql -c "SELECT client_addr, replay_lag FROM pg_stat_replication"`\n2. Check for heavy write load or long-running queries\n3. Verify network latency between primary and standbys\n4. Check standby I/O performance: `iostat -x 1 5`',
                recommendation: `PostgreSQL lag is ${max_lag_seconds.toFixed(1)}s. Watch it.`,
                display_value: val,
                raw_output: point.raw_output,
                template_data: { max_lag: max_lag_seconds.toFixed(1), warning_threshold: LAG_WARNING_THRESHOLD_SECONDS, unhealthy_threshold: LAG_UNHEALTHY_THRESHOLD_SECONDS },
            }
        }

        // Sub-second lag is normal for streaming replication
        return {
            status: 'healthy',
            status_reason: 'Maximum replication lag is **{{max_lag}}s**, within the healthy threshold of **{{warning_threshold}}s**.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { max_lag: max_lag_seconds.toFixed(1), warning_threshold: LAG_WARNING_THRESHOLD_SECONDS },
        }
    }
}

export default ReplicationLagChecker
