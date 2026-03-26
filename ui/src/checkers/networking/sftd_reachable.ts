/**
 * Checks if we can reach SFTd over HTTPS.
 *
 * Looks at network/sftd_reachable (boolean or string).
 * SFTd is what handles group calls with 3+ people.
 * If it's unreachable, those calls just die silently.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'
import { is_http_error_keyword } from '../checker_helpers'

export class SftdReachableChecker extends BaseChecker {
    readonly path: string = 'networking/sftd_reachable'
    readonly data_path: string = 'network/sftd_reachable'
    readonly name: string = 'SFTd HTTPS reachable'
    readonly category: string = 'Networking / Calling'
    readonly interest = 'Health' as const

    readonly requires_external_access: boolean = true
    readonly explanation: string = 'Verifies that the **SFTd** (Selective Forwarding Turn) server is reachable over HTTPS. SFTd handles conference calls with **3 or more participants**, so if it is unreachable, group calls silently fail.'

    check(data: DataLookup): CheckResult {
        // Skip when calling is not enabled in the deployment configuration
        if (data.config && !data.config.options.expect_calling) {
            return { status: 'not_applicable', status_reason: 'Calling is not enabled in the deployment configuration.' }
        }

        // Check before get() so the sentinel doesn't pollute the accessed points list
        if (data.is_not_applicable('network/sftd_reachable')) {
            return {
                status: 'not_applicable',
                status_reason: 'Gatherer ran from inside the cluster; SFTd external reachability cannot be tested from there.',
                recommendation: 'This needs to run from outside. Use --source external.',
            }
        }

        const point = data.get('network/sftd_reachable')

        // Target was not collected or not applicable for this run
        if (!point) {
            // Gatherer was on the admin host, can't test from outside
            if (data.is_not_applicable('network/sftd_reachable')) {
                return {
                    status: 'not_applicable',
                    status_reason: 'Gatherer ran from inside the cluster; SFTd external reachability cannot be tested from there.',
                    recommendation: 'This needs to run from outside. Use --source external.',
                }
            }

            return {
                status: 'gather_failure',
                status_reason: 'SFTd reachability data was not collected.',
                fix_hint: '1. Re-run the gatherer with the `sftd_reachable` target enabled\n2. Ensure the gatherer runs from **outside** the cluster (use `--source external`)\n3. Check gatherer logs for connection errors or timeouts',
                recommendation: 'SFTd reachability check wasn\'t run.',
            }
        }

        // Data point exists but the command failed, so value is null
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'SFTd reachability data was collected but the value is null, indicating the gathering command failed.',
                recommendation: 'Re-run the gatherer to collect SFTd reachability data.',
                raw_output: point.raw_output,
            }
        }

        const val: string | boolean = point.value as string | boolean

        // String result: check for connection error keywords before treating as healthy
        if (typeof val === 'string') {
            // A non-empty string that contains a network error keyword means the probe failed
            if (is_http_error_keyword(val)) {
                return {
                    status: 'unhealthy',
                    status_reason: `SFTd could not be reached: ${val}.`,
                    recommendation: 'SFTd is down or unreachable. Group calls with 3+ people won\'t work.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            if (val.length > 0) {
                return {
                    status: 'healthy',
                    status_reason: 'SFTd is reachable over **HTTPS**.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            return {
                status: 'unhealthy',
                status_reason: 'SFTd HTTPS endpoint returned an empty response, indicating it is **down or unreachable**.',
                fix_hint: '1. Test SFTd connectivity: `curl -vk https://<sftd-hostname>/healthz`\n2. Check if the SFTd pod is running: `kubectl get pods -l app=sftd`\n3. Check SFTd logs: `kubectl logs -l app=sftd --tail=50`\n4. Verify the SFTd service and ingress are configured: `kubectl get svc,ingress -l app=sftd`\n5. Check firewall rules allow HTTPS traffic to the SFTd endpoint',
                recommendation: 'SFTd is down or unreachable. Group calls with 3+ people won\'t work.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean true is good
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'SFTd is reachable over **HTTPS**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false means it's unreachable
        return {
            status: 'unhealthy',
            status_reason: 'SFTd is **not reachable** over HTTPS.',
            fix_hint: '1. Test SFTd connectivity: `curl -vk https://<sftd-hostname>/healthz`\n2. Check if the SFTd pod is running: `kubectl get pods -l app=sftd`\n3. Check SFTd logs: `kubectl logs -l app=sftd --tail=50`\n4. Verify the SFTd service and ingress are configured: `kubectl get svc,ingress -l app=sftd`\n5. Check firewall rules allow HTTPS traffic to the SFTd endpoint',
            recommendation: 'SFTd is down or unreachable. Group calls with 3+ people won\'t work.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default SftdReachableChecker
