/**
 * Checks federator service health and replicas.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederatorChecker extends BaseChecker {
    readonly path: string = 'wire_services/federator'
    readonly name: string = 'Federator service'
    readonly category: string = 'Wire Services'
    readonly interest = 'Health' as const
    readonly explanation: string = 'The federator is the gateway for inter-backend federation communication. If not running, federation is completely broken.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_federation) {
            // Check if federator pods exist anyway
            const point = data.get('wire_services/federator/healthy')
            if (point && point.value === true) {
                return { status: 'healthy', status_reason: 'Federator pods running (federation not declared as enabled in configuration).', display_value: 'running (undeclared)' }
            }
            return { status: 'not_applicable', status_reason: 'Federation is not enabled.' }
        }

        const point = data.get('wire_services/federator/healthy')
        if (!point) return { status: 'gather_failure', status_reason: 'Federator health data not collected.' }

        if (point.value === true || point.value === 'true') {
            return { status: 'healthy', status_reason: 'Federator is **running** and healthy.', display_value: 'healthy', raw_output: point.raw_output }
        }

        return {
            status: 'unhealthy',
            status_reason: 'Federator is **not running**. Federation is broken.',
            fix_hint: 'Ensure `tags.federation: true` in wire-server helm values and redeploy:\n```\nhelm upgrade wire-server wire/wire-server -f values.yaml\n```',
            display_value: 'not running',
            raw_output: point.raw_output,
        }
    }
}

export default FederatorChecker
