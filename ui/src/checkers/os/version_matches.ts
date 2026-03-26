/**
 * Checks that all node OS versions match Wire's supported Ubuntu releases.
 *
 * Consumes all os/<node>/version targets (one per node) and verifies the value
 * contains a supported Ubuntu version (18.04, 22.04, or 24.04).
 * Aggregates across nodes and gives you a single verdict.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// Ubuntu versions that Wire officially tests against
const SUPPORTED_VERSIONS: string[] = ['18.04', '22.04', '24.04']

export class VersionMatchesChecker extends BaseChecker {
    readonly path: string = 'os/version_matches'
    readonly name: string = 'OS version matches requirements'
    readonly category: string = 'OS / System'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies that all nodes run a **Wire-supported Ubuntu version** (18.04, 22.04, or 24.04). Unsupported OS versions may have incompatible kernel features or missing libraries that cause **unpredictable service failures**.'

    readonly requires_ssh: boolean = true

    check(data: DataLookup): CheckResult {
        // Get all version data points
        const points = data.find(/^os\/.*\/version$/)

        // Nothing collected
        if (points.length === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'OS version data was not collected from any node.',
                fix_hint: 'Ensure the gatherer script has **SSH access** to all nodes and can run `lsb_release -r` or read `/etc/os-release`. Verify that node hostnames in the inventory are correct.',
                recommendation: 'OS version data not collected.',
            }
        }

        // Parse out the node names path is like os/kubenode1/version
        const node_versions: { node: string; version: string }[] = points.map((point) => ({
            node: point.path.split('/')[1] ?? 'unknown',
            version: String(point.value),
        }))

        // Check for any unsupported versions
        const unsupported = node_versions.filter(
            (entry) => !SUPPORTED_VERSIONS.some((supported) => entry.version.includes(supported))
        )

        // Combine all the raw output
        const combined_raw: string = points
            .map((point) => point.raw_output)
            .filter(Boolean)
            .join('\n---\n')

        // Build a display summary
        const unique_versions = [...new Set(node_versions.map((entry) => entry.version))]
        const display_value: string = unique_versions.length === 1
            ? `${node_versions.length} nodes on ${unique_versions[0]}`
            : 'mixed versions'

        // Unsupported versions are a warning system still works but isn't tested
        if (unsupported.length > 0) {
            const details = unsupported
                .map((entry) => `${entry.node}: ${entry.version}`)
                .join(', ')

            return {
                status: 'warning',
                status_reason: '**{{count}}** node{{count_suffix}} running unsupported OS version{{version_suffix}}: {{details}}.',
                fix_hint: '1. Plan an OS upgrade to a supported Ubuntu version: **18.04**, **22.04**, or **24.04**.\n2. Check the current version on each node: `lsb_release -a`\n3. Back up critical data before upgrading.\n4. Follow the Ubuntu upgrade guide: `do-release-upgrade`\n\n**Note:** Wire is only tested against the supported versions. Other distributions or versions may work but are not guaranteed.',
                recommendation: `Unsupported OS version on: ${details}. Wire tests on Ubuntu 18.04, 22.04, and 24.04.`,
                display_value,
                raw_output: combined_raw,
                template_data: { count: unsupported.length, count_suffix: unsupported.length === 1 ? ' is' : 's are', version_suffix: unsupported.length === 1 ? '' : 's', details },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'All **{{total}}** node{{total_suffix}} running supported Ubuntu version{{version_display}}.',
            display_value,
            raw_output: combined_raw,
            template_data: { total: node_versions.length, total_suffix: node_versions.length === 1 ? '' : 's', version_display: unique_versions.length === 1 ? ` (${unique_versions[0]})` : 's' },
        }
    }
}

export default VersionMatchesChecker
