/**
 * Checks the NTP clock offset on the admin host.
 *
 * Looks at the host/ntp_offset target (float, milliseconds). When the offset
 * gets above 50 ms, Cassandra quorum operations start to fail. Above 200 ms,
 * you also run into TLS certificate validation issues. See JCT-158, JCT-156.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class NtpOffsetChecker extends BaseChecker {
    readonly path: string = 'host_admin/ntp_offset'
    readonly name: string = 'NTP clock offset (see: JCT-158, JCT-156)'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Measures the **NTP clock offset** in milliseconds on the admin host. Clock drift above **50 ms** causes Cassandra quorum failures, and above **200 ms** breaks TLS certificate validation entirely.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const point = data.get('host/ntp_offset')

        // Couldn't collect the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'NTP clock offset data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can run `timedatectl` or `chronyc tracking`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t collect the NTP clock offset data.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'NTP clock offset data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'NTP clock offset target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: number | string | boolean = point.value

        // Numeric value is offset in milliseconds
        if (typeof val === 'number') {
            // NTP offset is signed: positive = clock behind reference, negative = clock ahead.
            // Both directions are equally harmful, so compare the absolute value against thresholds.
            const abs_val = Math.abs(val)
            const abs_val_display = abs_val.toFixed(1)

            // Over 200 ms is critical TLS validation and Cassandra stop working
            if (abs_val >= 200) {
                return {
                    status: 'unhealthy',
                    status_reason: 'NTP clock offset is **{{abs_val_display}} ms**, which exceeds the **200 ms** critical threshold for TLS and Cassandra.',
                    fix_hint: '1. Check NTP service status: `systemctl status chronyd` or `systemctl status ntp`\n2. Force an immediate sync: `chronyc makestep` or `ntpdate -u pool.ntp.org`\n3. Verify NTP sources: `chronyc sources -v`\n4. If behind a firewall, ensure **UDP port 123** is open for NTP traffic.\n5. After fixing, verify offset: `chronyc tracking`',
                    recommendation: `NTP offset is ${abs_val_display} ms. At this level, TLS certificate validation and Cassandra quorum operations don't work. Get the clock synced right away.`,
                    display_value: val,
                    display_unit: 'ms',
                    raw_output: point.raw_output,
                    template_data: { abs_val_display, raw_val: val },
                }
            }

            // 50-200 ms is a warning Cassandra quorum can get into trouble
            if (abs_val >= 50) {
                return {
                    status: 'warning',
                    status_reason: 'NTP clock offset is **{{abs_val_display}} ms**, above the **50 ms** warning threshold where Cassandra quorum can get flaky.',
                    fix_hint: '1. Check NTP service status: `systemctl status chronyd` or `systemctl status ntp`\n2. Review NTP sources: `chronyc sources -v`\n3. Force a time step if needed: `chronyc makestep`\n4. Ensure the NTP server is reachable and **UDP port 123** is not blocked.',
                    recommendation: `NTP offset is ${abs_val_display} ms. Above 50 ms, Cassandra quorum operations can get flaky. Check what's going on with NTP.`,
                    display_value: val,
                    display_unit: 'ms',
                    raw_output: point.raw_output,
                    template_data: { abs_val_display, raw_val: val },
                }
            }

            // Under 50 ms is healthy
            return {
                status: 'healthy',
                status_reason: 'NTP clock offset is **{{abs_val_display}} ms**, well under the **50 ms** threshold.',
                display_value: val,
                display_unit: 'ms',
                raw_output: point.raw_output,
                template_data: { abs_val_display, raw_val: val },
            }
        }

        // Got a string value, can't really evaluate it
        return {
            status: 'warning',
            status_reason: 'NTP offset returned a non-numeric value (`{{val_string}}`), cannot evaluate clock drift.',
            fix_hint: '1. Check NTP service status: `systemctl status chronyd` or `systemctl status ntp`\n2. Verify `timedatectl` output manually on the admin host.\n3. The gatherer may have received an unexpected format — check the raw output for details.',
            recommendation: 'NTP offset returned a non-numeric value - can\'t tell if it\'s healthy.',
            display_value: String(val),
            raw_output: point.raw_output,
            template_data: { val_string: String(val) },
        }
    }
}

export default NtpOffsetChecker
