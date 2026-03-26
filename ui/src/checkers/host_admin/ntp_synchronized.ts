/**
 * Checks whether the admin host's system clock is NTP-synchronized.
 *
 * Looks at the host/ntp_synchronized target. If the clock isn't synced,
 * time drift breaks Cassandra quorum operations and other distributed
 * consensus mechanisms.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class NtpSynchronizedChecker extends BaseChecker {
    readonly path: string = 'host_admin/ntp_synchronized'
    readonly name: string = 'NTP synchronized'
    readonly category: string = 'Host / Admin machine'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies **NTP time synchronization** on the admin host. Without a synchronized clock, distributed systems like Cassandra lose quorum, TLS handshakes fail, and log timestamps become **unreliable**.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        const point = data.get('host/ntp_synchronized')

        // Couldn't collect the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'NTP synchronization data was not collected.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to the admin host and can run `timedatectl`. Check the script output for connection errors.',
                recommendation: 'Couldn\'t collect the NTP synchronization data.',
            }
        }

        // Gatherer ran but returned null (e.g. SSH succeeded but command failed)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'NTP synchronization data was collected but the value is null.',
                recommendation: 'Couldn\'t collect the NTP synchronization data.',
                raw_output: point.raw_output,
            }
        }

        const is_synchronized = coerce_boolean(point.value)

        // Clock is out of sync bad for distributed systems
        if (is_synchronized === false) {
            return {
                status: 'unhealthy',
                status_reason: 'System clock is **not NTP-synchronized**, which breaks distributed consensus and certificate validation.',
                fix_hint: '1. Check if an NTP service is installed and running:\n   ```\n   systemctl status chronyd || systemctl status ntp\n   ```\n2. If not installed, install chrony: `apt install chrony`\n3. Start and enable the service: `systemctl enable --now chronyd`\n4. Force an immediate sync: `chronyc makestep`\n5. Verify synchronization: `timedatectl | grep "synchronized"`',
                recommendation: 'System clock is not synchronized. Without NTP sync, Cassandra quorum operations and other consensus stuff break down.',
                display_value: is_synchronized,
                raw_output: point.raw_output,
            }
        }

        // coerce_boolean returned something other than true/false (unrecognized value)
        if (is_synchronized !== true) {
            return {
                status: 'gather_failure',
                status_reason: `NTP synchronization data has an unrecognized value: ${String(point.value)}`,
                recommendation: 'Couldn\'t interpret the NTP synchronization data.',
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'System clock is **NTP-synchronized**.',
            display_value: is_synchronized,
            raw_output: point.raw_output,
        }
    }
}

export default NtpSynchronizedChecker
