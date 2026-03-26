/**
 * Verifies that all the core Wire subdomains (nginz-https, nginz-ssl, webapp,
 * assets, account, teams, sftd) actually resolve in DNS. If even one of them
 * fails or returns NXDOMAIN, clients can't reach the service and everything breaks.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class SubdomainResolutionChecker extends BaseChecker {
    readonly path: string = 'dns/subdomain_resolution'
    readonly name: string = 'Resolution of all required subdomains'
    readonly category: string = 'DNS'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Checks that all required Wire subdomains (`nginz-https`, `nginz-ssl`, `webapp`, `assets`, `account`, `teams`, `sftd`) resolve in DNS. Missing records prevent clients from connecting to Wire services **entirely**.'

    check(data: DataLookup): CheckResult {
        // Skip when DNS is not available
        if (data.config && !data.config.options.has_dns) {
            return { status: 'not_applicable', status_reason: 'DNS is not available in this deployment.' }
        }

        const point = data.get_applicable('dns/subdomain_resolution') ?? data.get('direct/dns/subdomain_resolution')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Subdomain resolution data was not collected.',
                fix_hint: 'Ensure the gatherer can perform DNS lookups using `dig` or `nslookup`. Check that the domain is correctly configured in the gathering parameters and that the machine has **DNS resolution** working.',
                recommendation: 'Resolution of all required subdomains data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Subdomain resolution data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Subdomain resolution target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // Build a domain-aware recommendation when possible
        const domain: string = data.config?.cluster.domain ?? ''
        const subdomain_list: string = domain
            ? `nginz-https.${domain}, nginz-ssl.${domain}, webapp.${domain}, assets.${domain}, account.${domain}, teams.${domain}, sftd.${domain}`
            : 'nginz-https, nginz-ssl, webapp, assets, account, teams, sftd'
        const fail_recommendation: string = `DNS resolution failed for some subdomains (${subdomain_list}). All core records should point to the same IP.`

        if (typeof val === 'string') {
            const lower: string = val.toLowerCase()

            // Known DNS error indicators — any of these means resolution failed
            const error_keywords: string[] = [
                'nxdomain', 'failed', 'servfail', 'timeout', 'refused',
                'connection error', 'unreachable', 'no servers', 'network error',
            ]
            const has_error: boolean = error_keywords.some(kw => lower.includes(kw))

            if (has_error) {
                return {
                    status: 'unhealthy',
                    status_reason: `DNS resolution failed for some subdomains: response contains failure indicators.`,
                    recommendation: fail_recommendation,
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { domain_display: domain || '<your-domain>' },
                }
            }

            // Whitelist: only treat as healthy if the string looks like a successful result.
            // The Python target returns comma-separated subdomain names on success, or the
            // health_info contains "resolved" / IP addresses.
            const ip_pattern: RegExp = /\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/
            const looks_healthy: boolean =
                lower.includes('resolved') ||
                lower.includes('nginz') ||
                lower.includes('webapp') ||
                ip_pattern.test(val)

            if (val.length > 0 && looks_healthy) {
                return {
                    status: 'healthy',
                    status_reason: 'All required Wire subdomains resolved **successfully**.',
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }

            // Non-empty string that doesn't match known-good or known-bad patterns —
            // flag as warning so it gets human attention rather than silently passing
            if (val.length > 0) {
                return {
                    status: 'warning',
                    status_reason: `DNS resolution returned an unrecognized response: "${val}".`,
                    recommendation: `Unexpected DNS response. Verify subdomain resolution manually for: ${subdomain_list}.`,
                    display_value: val,
                    raw_output: point.raw_output,
                }
            }
        }

        // Boolean true or positive number means healthy
        if (val === true || (typeof val === 'number' && val > 0)) {
            return {
                status: 'healthy',
                status_reason: 'All required Wire subdomains resolved **successfully**.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Anything falsy means it failed
        return {
            status: 'unhealthy',
            status_reason: 'DNS resolution **failed** or returned a falsy value for required Wire subdomains.',
            fix_hint: '1. Verify each required subdomain resolves:\n   ```\n   for sub in nginz-https nginz-ssl webapp assets account teams sftd; do\n     echo "$sub.{{domain_display}}: $(dig +short $sub.{{domain_display}})"\n   done\n   ```\n2. Add missing **A** or **CNAME** records in your DNS provider.\n3. Ensure all subdomains point to the **same load balancer IP**.\n4. Verify DNS propagation: `dig +trace <subdomain>.{{domain_display}}`',
            recommendation: fail_recommendation,
            display_value: val,
            raw_output: point.raw_output,
            template_data: { domain_display: domain || '<your-domain>' },
        }
    }
}

export default SubdomainResolutionChecker
