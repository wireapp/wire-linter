/**
 * Flags problematic image pull policy combinations.
 *
 * :latest with IfNotPresent means nodes may run different versions of
 * the "same" tag. This causes inconsistent behavior across pods.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

interface PolicyIssue {
    service: string
    container: string
    image: string
    policy: string
    issue: string
}

export class ImagePullPolicyChecker extends BaseChecker {
    readonly path: string = 'kubernetes/image_pull_policy'
    readonly name: string = 'Image pull policy'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string =
        'Using the `:latest` tag with `IfNotPresent` pull policy means different nodes ' +
        'may cache different versions of the "same" tag, causing inconsistent behavior. ' +
        'Use specific version tags or set `imagePullPolicy: Always` with `:latest`.'

    check(data: DataLookup): CheckResult {
        const issues: PolicyIssue[] = []
        let services_checked: number = 0

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            let details: {
                containers?: {
                    name: string
                    image: string
                    image_pull_policy: string
                }[]
            }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            for (const container of details.containers ?? []) {
                const image: string = container.image ?? ''
                const policy: string = container.image_pull_policy ?? 'IfNotPresent'

                // Extract tag — look for ':' only after the last '/' to avoid matching registry port numbers
                const last_slash: number = image.lastIndexOf('/')
                const colon_after_repo: number = image.indexOf(':', last_slash + 1)
                const tag: string = colon_after_repo !== -1 ? image.slice(colon_after_repo + 1) : ''
                const is_latest: boolean = tag === 'latest' || tag === ''

                // :latest with IfNotPresent = nodes may have different cached versions
                if (is_latest && policy !== 'Always') {
                    issues.push({
                        service,
                        container: container.name,
                        image,
                        policy,
                        issue: '`:latest` tag with non-Always pull policy',
                    })
                }
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment details data collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        if (issues.length > 0) {
            const summary: string = issues
                .map((i: PolicyIssue) =>
                    `**${i.service}**/${i.container}: \`${i.image}\` with policy \`${i.policy}\``)
                .join('\n- ')

            return {
                status: 'warning',
                status_reason: `{{issue_count}} container(s) use \`:latest\` without \`Always\` pull policy.`,
                fix_hint: 'Either use specific version tags (recommended):\n```yaml\nimage: quay.io/wire/brig:4.40.0\n```\nOr set pull policy to Always:\n```yaml\nimagePullPolicy: Always\n```',
                recommendation: `Pull policy issues:\n- ${summary}`,
                display_value: `${issues.length} issue(s)`,
                template_data: { issue_count: issues.length },
            }
        }

        return {
            status: 'healthy',
            status_reason: `All containers across ${services_checked} service(s) have appropriate image pull policies.`,
            display_value: `${services_checked} OK`,
            template_data: { issue_count: 0 },
        }
    }
}

export default ImagePullPolicyChecker
