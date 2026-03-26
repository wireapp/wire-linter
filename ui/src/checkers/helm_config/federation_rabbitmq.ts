/**
 * Verifies RabbitMQ is configured in all services that need it for federation.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class FederationRabbitmqChecker extends BaseChecker {
    readonly path: string = 'helm_config/federation_rabbitmq'
    readonly name: string = 'Federation RabbitMQ dependency'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Federation requires RabbitMQ for async event processing. Brig, galley, cannon, and background-worker must all have `rabbitmq.host` configured.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.expect_federation) {
            return { status: 'not_applicable', status_reason: 'Federation is not enabled.' }
        }

        const point = data.get('config/federation_rabbitmq_config')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Federation RabbitMQ config not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        const all_configured: boolean = parsed.all_configured as boolean ?? false
        const services = ['brig', 'galley', 'cannon', 'background-worker']
        const missing: string[] = services.filter(s => !parsed![s.replace('-', '_')] && !parsed![s])

        if (!all_configured) {
            return {
                status: 'unhealthy',
                status_reason: `Federation requires RabbitMQ but these services have no \`rabbitmq.host\` configured: **${missing.join(', ')}**.`,
                fix_hint: 'Set rabbitmq.host in helm values for each affected service.',
                display_value: `${services.length - missing.length}/${services.length} configured`,
                raw_output: point.raw_output,
            }
        }

        return { status: 'healthy', status_reason: 'RabbitMQ host configured in all 4 federation-dependent services.', display_value: 'all configured', raw_output: point.raw_output }
    }
}

export default FederationRabbitmqChecker
