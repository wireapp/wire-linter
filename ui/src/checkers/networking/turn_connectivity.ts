/**
 * Checks TURN/Coturn UDP connectivity on port 3478 and the relay range.
 *
 * Consumes the network/turn_connectivity target (boolean or string).
 * If TURN relays aren't working, voice and video calls break silently
 * for users behind restrictive firewalls or symmetric NATs.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class TurnConnectivityChecker extends BaseChecker {
    readonly path: string = 'networking/turn_connectivity'
    readonly data_path: string = 'network/turn_connectivity'
    readonly name: string = 'TURN/Coturn UDP connectivity'
    readonly category: string = 'Networking / Calling'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Verifies that **TURN/Coturn** relays are reachable on UDP port `3478` and the relay port range. Users behind restrictive firewalls or symmetric NATs rely on TURN to establish voice and video calls, so broken relays cause silent call failures for those users.'

    check(data: DataLookup): CheckResult {
        // Skip when calling is not enabled
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled in the deployment configuration.' }
        }

        const point = data.get_applicable('network/turn_connectivity')

        // Target was not collected or not applicable for this run
        if (!point) {
            // Gatherer ran on the admin host, can't test external TURN from there
            if (data.is_not_applicable('network/turn_connectivity')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'Gatherer ran from inside the cluster; external TURN connectivity cannot be tested from there.',
                    recommendation: 'This check requires running the gatherer from an internet-connected machine. Re-run with --source external to test TURN connectivity from outside.',
                }
            }

            return {
                status: 'gather_failure',
                status_reason: 'TURN/Coturn UDP connectivity data was not collected.',
                fix_hint: '1. Re-run the gatherer with the `turn_connectivity` target enabled\n2. Ensure the gatherer runs from **outside** the cluster (use `--source external`)\n3. Check gatherer logs for connection errors or timeouts',
                recommendation: 'TURN/Coturn UDP connectivity data not collected.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String value: non-empty means connectivity works
        if (typeof val === 'string') {
            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'TURN/Coturn UDP connectivity on port `3478` and relay range is **working**.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'TURN/Coturn UDP connectivity test **failed** on port `3478` and/or the relay range.',
                fix_hint: '1. Test TURN port: `nc -zvu <turn-hostname> 3478`\n2. Verify Coturn is running: `kubectl get pods -l app=coturn` or `systemctl status coturn`\n3. Check Coturn logs: `kubectl logs -l app=coturn --tail=50` or `journalctl -u coturn`\n4. Test relay range connectivity: `nc -zvu <turn-hostname> 32768-65535` (sample a few ports)\n5. Check firewall rules allow UDP traffic on port `3478` and the relay range (`32768-65535`)\n6. Verify cloud provider security groups/network ACLs allow inbound UDP',
                recommendation: 'TURN/Coturn UDP connectivity failed (port 3478 + relay range). Voice/video silently breaks for users behind restrictive firewalls.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true: TURN is reachable
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'TURN/Coturn UDP connectivity on port `3478` and relay range is **working**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false: TURN connectivity failed
        return {
            status: 'unhealthy',
            status_reason: 'TURN/Coturn UDP connectivity test **failed** on port `3478` and/or the relay range.',
            fix_hint: '1. Test TURN port: `nc -zvu <turn-hostname> 3478`\n2. Verify Coturn is running: `kubectl get pods -l app=coturn` or `systemctl status coturn`\n3. Check Coturn logs: `kubectl logs -l app=coturn --tail=50` or `journalctl -u coturn`\n4. Test relay range connectivity: `nc -zvu <turn-hostname> 32768-65535` (sample a few ports)\n5. Check firewall rules allow UDP traffic on port `3478` and the relay range (`32768-65535`)\n6. Verify cloud provider security groups/network ACLs allow inbound UDP',
            recommendation: 'TURN/Coturn UDP connectivity failed (port 3478 + relay range). Voice/video silently breaks for users behind restrictive firewalls.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default TurnConnectivityChecker
