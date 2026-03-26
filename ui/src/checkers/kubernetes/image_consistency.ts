/**
 * Checks that Wire services are running consistent image versions.
 *
 * Wire releases ship all core services at the same version. Mixed
 * versions indicate a partial upgrade or botched rollout.
 *
 * Consumes: kubernetes/deployments/details/<service> (all 8)
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { WIRE_CORE_SERVICES } from '../constants'
import type { DataLookup } from '../data_lookup'

export class ImageConsistencyChecker extends BaseChecker {
    readonly path: string = 'kubernetes/image_consistency'
    readonly name: string = 'Container image consistency'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string =
        'Wire releases ship all core services at the **same version**. During a botched ' +
        'rollout, some services may be running a different image version than others, ' +
        'causing incompatibility issues between services.'

    check(data: DataLookup): CheckResult {
        // Collect image tags per service
        const service_images: { service: string; image: string; tag: string }[] = []
        let services_checked: number = 0
        const raw_outputs: string[] = []

        for (const service of WIRE_CORE_SERVICES) {
            const point = data.get_applicable(`kubernetes/deployments/details/${service}`)
            if (!point) continue

            if (point.raw_output) raw_outputs.push(point.raw_output)

            let details: { containers?: { name: string; image: string }[] }
            try { details = JSON.parse(String(point.value)) } catch { continue }

            services_checked++

            // Take the first container's image (the main service container)
            const containers = details.containers ?? []
            if (containers.length > 0) {
                const first_container = containers[0]
                const image: string = first_container?.image ?? ''
                // Extract tag: only a colon AFTER the last slash is a tag separator
                // (colons before that are registry port numbers, e.g. registry.example.com:5000/wire/brig)
                const last_slash: number = image.lastIndexOf('/')
                const colon_after_repo: number = image.indexOf(':', last_slash + 1)
                const tag: string = colon_after_repo !== -1 ? image.slice(colon_after_repo + 1) : 'latest'
                service_images.push({ service, image, tag })
            }
        }

        if (services_checked === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No deployment details data collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        // Find unique tags (ignoring the registry/repository prefix, just comparing tags)
        // Wire images typically share a version tag like "4.40.0"
        const unique_tags: Set<string> = new Set(
            service_images.map((si: { tag: string }) => si.tag)
        )

        if (unique_tags.size <= 1) {
            const tags_array: string[] = [...unique_tags]
            const tag: string = tags_array.length > 0 ? tags_array[0]! : 'unknown'
            return {
                status: 'healthy',
                status_reason: `All ${services_checked} service(s) running consistent image tag: \`${tag}\`.`,
                display_value: tag,
                raw_output: raw_outputs.join('\n') || undefined,
                template_data: { tag_count: unique_tags.size },
            }
        }

        // Group services by tag
        const by_tag: Record<string, string[]> = {}
        for (const si of service_images) {
            if (!by_tag[si.tag]) by_tag[si.tag] = []
            by_tag[si.tag]!.push(si.service)
        }

        const breakdown: string = Object.entries(by_tag)
            .map(([tag, services]: [string, string[]]) =>
                `\`${tag}\`: ${services.map((s: string) => `**${s}**`).join(', ')}`)
            .join('\n- ')

        return {
            status: 'warning',
            status_reason: `**{{tag_count}}** different image tags found across services.`,
            fix_hint: 'Run `helm upgrade` to align all services to the same version:\n```\nhelm upgrade wire-server wire/wire-server -f values.yaml\n```',
            recommendation: `Image tags:\n- ${breakdown}`,
            display_value: `${unique_tags.size} versions`,
            raw_output: raw_outputs.join('\n') || undefined,
            template_data: { tag_count: unique_tags.size },
        }
    }
}

export default ImageConsistencyChecker
