/**
 * Flags ingresses without TLS configuration.
 *
 * Ingresses without TLS serve traffic over plain HTTP — unencrypted.
 *
 * Consumes: kubernetes/ingress/tls_config
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class IngressTlsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/ingress_tls'
    readonly name: string = 'Ingress TLS configuration'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/ingress/tls_config'
    readonly explanation: string =
        'Ingresses without TLS configuration serve traffic over **plain HTTP**. ' +
        'Every production ingress host should be covered by a TLS entry to ensure ' +
        'encrypted connections.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/ingress/tls_config')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Ingress TLS data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            total_ingresses?: number
            with_tls?: number
            without_tls?: number
            details?: { name: string; namespace: string; uncovered_hosts: string[]; has_tls: boolean }[]
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse TLS config data.', raw_output: point.raw_output }
        }

        if (typeof parsed !== 'object' || parsed === null) {
            return { status: 'gather_failure', status_reason: 'TLS config data is not a JSON object.', raw_output: point.raw_output }
        }

        const total: number = parsed.total_ingresses ?? 0
        const without_tls: number = parsed.without_tls ?? 0

        if (total === 0) {
            return {
                status: 'not_applicable',
                status_reason: 'No ingress resources found.',
                raw_output: point.raw_output,
            }
        }

        if (without_tls > 0) {
            const no_tls_ingresses: string = (parsed.details ?? [])
                .filter((d: { has_tls: boolean }) => !d.has_tls)
                .map((d: { name: string; namespace: string }) => `**${d.namespace}/${d.name}**`)
                .join(', ')

            // Check for hosts not covered by TLS even on ingresses that have TLS
            const uncovered: string[] = (parsed.details ?? [])
                .flatMap((d: { uncovered_hosts: string[] }) => d.uncovered_hosts ?? [])

            const uncovered_note: string = uncovered.length > 0
                ? ` Additionally, ${uncovered.length} host(s) are not covered by TLS entries.`
                : ''

            return {
                status: 'warning',
                status_reason: '**{{without_tls}}** ingress(es) have no TLS configuration: {{{no_tls_ingresses}}}.{{uncovered_note}}',
                fix_hint: 'Add TLS to your ingress configuration:\n```yaml\nspec:\n  tls:\n  - hosts:\n    - your.domain.com\n    secretName: your-tls-secret\n```\nOr use cert-manager for automatic certificate management.',
                display_value: `${without_tls} without TLS`,
                raw_output: point.raw_output,
                template_data: { without_tls, no_tls_ingresses, uncovered_note },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All {{total}} ingress(es) have TLS configured.',
            display_value: `${total} with TLS`,
            raw_output: point.raw_output,
            template_data: { total },
        }
    }
}

export default IngressTlsChecker
