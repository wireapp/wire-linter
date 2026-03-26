/**
 * Checks whether webapp backend URLs have been changed from placeholder values.
 *
 * Consumes the config/webapp_backend_urls target (boolean or string).
 * Placeholder URLs like «api.example.com» are the #1 cause of
 * «ERROR 6» after a fresh Wire install.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class WebappBackendUrlsChecker extends BaseChecker {
    readonly path: string = 'helm_config/webapp_backend_urls'
    readonly name: string = 'Webapp backend URLs not placeholder values'
    readonly category: string = 'Helm / Config Validation'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Detects **placeholder** backend URLs (like `api.example.com`) in the webapp configuration. Unreplaced placeholders are the most common cause of **"ERROR 6"** after a fresh Wire install.'

    check(data: DataLookup): CheckResult {
        const point = data.get('config/webapp_backend_urls')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Webapp backend URL data was not collected.',
                fix_hint: '1. Verify the webapp ConfigMap exists:\n   ```\n   kubectl get configmap webapp -n wire -o yaml\n   ```\n2. Re-run the gatherer ensuring the `config/webapp_backend_urls` target succeeds.',
                recommendation: 'Couldn\'t collect webapp backend URL data.',
            }
        }

        const val: string | boolean = point.value as string | boolean

        // New structured return values from target: "ok", "error", "warning"
        if (val === 'ok') {
            return {
                status: 'healthy',
                status_reason: 'Webapp backend URLs are properly configured (no placeholder patterns detected).',
                display_value: 'configured',
                raw_output: point.raw_output,
            }
        }

        if (val === 'error') {
            return {
                status: 'unhealthy',
                status_reason: 'Webapp backend URLs contain placeholder values.',
                recommendation: 'Webapp config still points to placeholder URLs (e.g., api.example.com, CHANGE_ME). This is the most common cause of «ERROR 6» after a fresh install. Replace them with the actual backend service URLs.',
                display_value: 'placeholder URLs',
                raw_output: point.raw_output,
            }
        }

        if (val === 'warning') {
            return {
                status: 'warning',
                status_reason: 'Webapp backend URLs reference localhost/127.0.0.1.',
                recommendation: 'Localhost URLs may be valid for single-node or co-located deployments (e.g., local Redis sidecar). Verify this is intentional — if this is a multi-node deployment, these should be replaced with real service addresses.',
                display_value: 'localhost URLs',
                raw_output: point.raw_output,
            }
        }

        // Legacy boolean support (old gatherer data)
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Webapp backend URLs are properly configured (not placeholders).',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false — old gatherer flagged placeholder URLs
        return {
            status: 'unhealthy',
            status_reason: 'Webapp backend URLs are still set to placeholder values.',
            recommendation: 'Webapp config still points to placeholder URLs (e.g., api.example.com). This is the most common cause of «ERROR 6» after a fresh install.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default WebappBackendUrlsChecker
