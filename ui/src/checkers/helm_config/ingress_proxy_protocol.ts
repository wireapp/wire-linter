/**
 * Reports the ingress-nginx proxy protocol configuration.
 *
 * Consumes the config/ingress_proxy_protocol target (string: "enabled",
 * "disabled", "not_found"). If nginx and the load balancer disagree on
 * proxy protocol, requests fail with 400 errors or get silently misrouted.
 * See WPB-17802.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class IngressProxyProtocolChecker extends BaseChecker {
    readonly path: string = 'helm_config/ingress_proxy_protocol'
    readonly name: string = 'ingress-nginx proxy protocol config (see: WPB-17802)'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports the **PROXY protocol** setting in `ingress-nginx`. If nginx and the load balancer disagree on whether PROXY protocol is in use, requests fail with **400 errors** or get silently misrouted.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/ingress_proxy_protocol')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: '`ingress-nginx` proxy protocol configuration data was not collected.',
                fix_hint: '1. Check if the ingress-nginx ConfigMap exists:\n   ```\n   kubectl get configmap -n ingress-nginx\n   ```\n2. Re-run the gatherer ensuring the `config/ingress_proxy_protocol` target succeeds.',
                recommendation: 'Couldn\'t get ingress-nginx proxy protocol config data.',
            }
        }

        const val = String(point.value ?? '').toLowerCase()

        // ConfigMap not found — data was collected, but the ConfigMap doesn't
        // exist in any known namespace/name. This isn't a gather failure (the
        // target ran fine), it means ingress-nginx either isn't deployed or
        // uses a non-standard ConfigMap name.
        if (val === 'not_found') {
            return {
                status: 'not_applicable',
                status_reason: '`ingress-nginx` ConfigMap was not found in any known namespace.',
                recommendation: 'ingress-nginx ConfigMap not found. If ingress-nginx is deployed, it may use a non-standard ConfigMap name or namespace.',
                display_value: 'not found',
                raw_output: point.raw_output,
            }
        }

        // Proxy protocol enabled, make sure load balancer sends headers
        if (val === 'enabled') {
            return {
                status: 'healthy',
                status_reason: 'PROXY protocol is **enabled** in `ingress-nginx`.',
                recommendation: 'PROXY protocol is enabled in ingress-nginx. Make sure your load balancer sends PROXY headers, or requests will fail with 400 errors.',
                display_value: 'enabled',
                raw_output: point.raw_output,
            }
        }

        // Proxy protocol disabled, load balancer shouldn't send headers
        if (val === 'disabled') {
            return {
                status: 'healthy',
                status_reason: 'PROXY protocol is **disabled** in `ingress-nginx`.',
                recommendation: 'PROXY protocol is disabled in ingress-nginx. Make sure your load balancer isn\'t sending PROXY headers, or nginx will choke and fail.',
                display_value: 'disabled',
                raw_output: point.raw_output,
            }
        }

        // Unexpected value
        return {
            status: 'warning',
            status_reason: 'Unexpected proxy protocol configuration value: `{{proxy_value}}`.',
            fix_hint: '1. Inspect the ingress-nginx ConfigMap:\n   ```\n   kubectl get configmap -n ingress-nginx -o yaml | grep proxy-protocol\n   ```\n2. Set `use-proxy-protocol` to `true` or `false` in the ingress-nginx ConfigMap\n3. Apply the fix:\n   ```\n   kubectl edit configmap -n ingress-nginx ingress-nginx-controller\n   ```',
            recommendation: 'Unexpected proxy protocol configuration value.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { proxy_value: val },
        }
    }
}

export default IngressProxyProtocolChecker
