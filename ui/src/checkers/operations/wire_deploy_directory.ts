/**
 * Checks wire-server-deploy directory on the admin host.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class WireDeployDirectoryChecker extends BaseChecker {
    readonly path: string = 'operations/wire_deploy_directory'
    readonly name: string = 'Wire-server-deploy directory'
    readonly category: string = 'Operations / Tooling'
    readonly interest = 'Setup' as const
    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Wire-managed clusters have `~/wire-server-deploy/` on the admin host with ansible playbooks, helm values, and deployment artifacts.'

    check(data: DataLookup): CheckResult {
        if (data.config && !data.config.options.wire_managed_cluster) {
            return { status: 'not_applicable', status_reason: 'Not a Wire-managed cluster.' }
        }

        const point = data.get('host/wire_deploy_directory')
        if (!point?.value) return { status: 'gather_failure', status_reason: 'Wire deploy directory check not collected.' }

        let parsed: Record<string, unknown> | null = null
        try { parsed = JSON.parse(String(point.value)) } catch { /* ignore */ }
        if (!parsed) return { status: 'gather_failure', status_reason: 'Could not parse data.' }

        if (!(parsed.exists as boolean)) {
            return { status: 'warning', status_reason: 'Wire-managed cluster declared but `~/wire-server-deploy/` **not found** on admin host.', raw_output: point.raw_output }
        }

        const subdirs: string[] = (parsed.subdirectories as string[]) ?? []
        const inv_dirs: string[] = (parsed.inventory_dirs as string[]) ?? []

        return {
            status: 'healthy',
            status_reason: `Wire-server-deploy directory found: ${subdirs.length} items${inv_dirs.length > 0 ? `, inventory: ${inv_dirs.join(', ')}` : ''}.`,
            display_value: `found (${subdirs.length} items)`,
            raw_output: point.raw_output,
        }
    }
}

export default WireDeployDirectoryChecker
