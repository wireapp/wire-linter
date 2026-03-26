/**
 * Makes sure you've got SPF and DMARC records set up for Wire's email domain.
 * If these aren't configured, password resets and team invitations get rejected
 * or end up in spam folders at recipient mail servers (see WPB-18153).
 * The target gives us four states: «spf+dmarc», «spf_only», «dmarc_only», or «missing».
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class EmailDnsRecordsChecker extends BaseChecker {
    readonly path: string = 'dns/email_dns_records'
    readonly name: string = 'SPF and DMARC email DNS records (see: WPB-18153)'
    readonly category: string = 'DNS'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that **SPF** and **DMARC** DNS records exist for the Wire email domain. Without these records, password reset and team invitation emails get rejected or land in **spam** at recipient mail servers.'

    check(data: DataLookup): CheckResult {
        // Skip when DNS is not available
        if (data.config && !data.config.options.has_dns) {
            return { status: 'not_applicable', status_reason: 'DNS is not available in this deployment.' }
        }

        const point = data.get_applicable('dns/email_dns_records') ?? data.get('direct/dns/email_dns_records')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Email DNS records (**SPF**, **DMARC**) data was not collected.',
                fix_hint: 'Ensure the gatherer can perform DNS lookups using `dig`. Check that the domain is correctly configured in the gathering parameters and that the machine has **DNS resolution** working (`dig +short TXT example.com`).',
                recommendation: 'Email DNS records (SPF, DMARC) data not collected.',
            }
        }

        const val = String(point.value ?? '').toLowerCase()

        // Use the cluster domain from config when available, fall back to
        // extracting it from metadata/raw_output for older JSONL files
        const domain: string = data.config?.cluster.domain ?? this._extract_domain(point)

        if (val === 'spf+dmarc') {
            return {
                status: 'healthy',
                status_reason: 'Both **SPF** and **DMARC** DNS records are configured for **{{domain_display}}**.',
                display_value: 'SPF + DMARC',
                raw_output: point.raw_output,
                template_data: { domain_display: domain || 'the email domain' },
            }
        }

        if (val === 'spf_only') {
            const domain_display: string = domain || '<your-domain>'

            return {
                status: 'warning',
                status_reason: '**SPF** record found but **DMARC** is missing for **{{domain_display}}**.',
                fix_hint: '1. Add a **DMARC** TXT DNS record in your DNS provider:\n   - **Record type:** TXT\n   - **Record name:** `_dmarc.{{domain_display}}`\n   - **Record value:** `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@{{domain_display}}; pct=100`\n2. After adding, verify with:\n   ```\n   dig +short TXT _dmarc.{{domain_display}}\n   ```\n3. Allow up to **48 hours** for DNS propagation.',
                recommendation: [
                    `SPF record found but DMARC is missing for ${domain_display}. Wire emails may be rejected by strict recipient mail servers.`,
                    '',
                    'Add a DMARC TXT DNS record:',
                    `  Record type: TXT`,
                    `  Record name: _dmarc.${domain_display}`,
                    `  Record value: v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@${domain_display}; pct=100`,
                    '',
                    'Set this in your DNS provider. After adding, verify with: dig +short TXT _dmarc.' + domain_display,
                ].join('\n'),
                display_value: 'SPF only, no DMARC',
                raw_output: point.raw_output,
                template_data: { domain_display },
            }
        }

        if (val === 'dmarc_only') {
            const domain_display: string = domain || '<your-domain>'

            return {
                status: 'warning',
                status_reason: '**DMARC** record found but **SPF** is missing for **{{domain_display}}**.',
                fix_hint: '1. Add an **SPF** TXT DNS record in your DNS provider:\n   - **Record type:** TXT\n   - **Record name:** `{{domain_display}}`\n   - **Record value:** `v=spf1 include:_spf.your-email-provider.com ~all`\n2. Replace the `include:` with your actual mail server.\n3. After adding, verify with:\n   ```\n   dig +short TXT {{domain_display}}\n   ```\n4. Use `~all` for softfail or `-all` for hardfail.',
                recommendation: [
                    `DMARC record found but SPF is missing for ${domain_display}. Wire emails may be marked as spam.`,
                    '',
                    'Add an SPF TXT DNS record:',
                    `  Record type: TXT`,
                    `  Record name: ${domain_display}`,
                    `  Record value: v=spf1 include:_spf.your-email-provider.com ~all`,
                    '',
                    '(Replace the include: with your actual mail server. Use ~all for softfail or -all for hardfail.)',
                    'After adding, verify with: dig +short TXT ' + domain_display,
                ].join('\n'),
                display_value: 'DMARC only, no SPF',
                raw_output: point.raw_output,
                template_data: { domain_display },
            }
        }

        if (val === 'missing') {
            const domain_display: string = domain || '<your-domain>'

            return {
                status: 'unhealthy',
                status_reason: 'Neither **SPF** nor **DMARC** DNS records are configured for **{{domain_display}}**.',
                fix_hint: '1. Add an **SPF** TXT DNS record:\n   - **Record type:** TXT\n   - **Record name:** `{{domain_display}}`\n   - **Record value:** `v=spf1 include:_spf.your-email-provider.com ~all`\n2. Add a **DMARC** TXT DNS record:\n   - **Record type:** TXT\n   - **Record name:** `_dmarc.{{domain_display}}`\n   - **Record value:** `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@{{domain_display}}; pct=100`\n3. Replace the SPF `include:` with your actual mail server.\n4. After adding both, verify:\n   ```\n   dig +short TXT {{domain_display}}\n   dig +short TXT _dmarc.{{domain_display}}\n   ```',
                recommendation: [
                    `Neither SPF nor DMARC DNS records are configured for ${domain_display}.`,
                    'Wire emails (password reset, team invitations) will be rejected or land in spam.',
                    '',
                    '1. Add an SPF TXT DNS record:',
                    `   Record type: TXT`,
                    `   Record name: ${domain_display}`,
                    `   Record value: v=spf1 include:_spf.your-email-provider.com ~all`,
                    '',
                    '2. Add a DMARC TXT DNS record:',
                    `   Record type: TXT`,
                    `   Record name: _dmarc.${domain_display}`,
                    `   Record value: v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@${domain_display}; pct=100`,
                ].join('\n'),
                display_value: 'SPF missing, DMARC missing',
                raw_output: point.raw_output,
                template_data: { domain_display },
            }
        }

        return {
            status: 'warning',
            status_reason: 'Email DNS records returned an unexpected value: `{{val}}`.',
            fix_hint: 'The gatherer returned an unrecognized value. Check the raw output for details and verify DNS records manually:\n```\ndig +short TXT {{domain_display}}\ndig +short TXT _dmarc.{{domain_display}}\n```',
            recommendation: 'Unexpected email DNS records value.',
            display_value: val,
            raw_output: point.raw_output,
            template_data: { val, domain_display: domain || '<your-domain>' },
        }
    }

    /** Try to extract the domain from the metadata or raw output. */
    private _extract_domain(point: { metadata?: { health_info?: string }, raw_output?: string }): string {
        // The metadata usually has something like "Missing email DNS record(s) for robot-takeover.com: DMARC. ..."
        const health_info: string = point.metadata?.health_info ?? ''
        const domain_match: RegExpMatchArray | null = health_info.match(/for\s+([\w.-]+):/)
        if (domain_match && domain_match[1]) return domain_match[1]

        // Otherwise check the raw output from the dig commands, they mention the domain too
        const raw: string = point.raw_output ?? ''
        const raw_match: RegExpMatchArray | null = raw.match(/dig\s+.*?TXT\s+([\w.-]+)/)
        if (raw_match && raw_match[1]) return raw_match[1]

        return ''
    }
}

export default EmailDnsRecordsChecker
