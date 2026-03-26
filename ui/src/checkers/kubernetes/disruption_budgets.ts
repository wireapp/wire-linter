/**
 * Checks whether Pod Disruption Budgets exist for Wire services.
 *
 * Without PDBs, a kubectl drain during node maintenance can evict
 * all pods simultaneously, causing a complete service outage.
 *
 * Consumes: kubernetes/pods/disruption_budgets
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_json_value, type DataLookup } from '../data_lookup'

export class DisruptionBudgetsChecker extends BaseChecker {
    readonly path: string = 'kubernetes/disruption_budgets'
    readonly name: string = 'Pod Disruption Budgets'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly data_path: string = 'kubernetes/pods/disruption_budgets'
    readonly explanation: string =
        '**Pod Disruption Budgets** (PDBs) prevent all pods of a service from being ' +
        'evicted simultaneously during voluntary disruptions like node drains. Without ' +
        'PDBs, routine maintenance can cause complete service outages.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pods/disruption_budgets')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'PDB data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        interface PdbData {
            pdb_count?: number
            pdbs?: {
                name: string
                min_available: number | string | null
                max_unavailable: number | string | null
                disruptions_allowed: number
                current_healthy: number
                desired_healthy: number
                selector_labels: Record<string, string>
            }[]
        }
        const parsed = parse_json_value<PdbData>(point)
        if (!parsed) {
            return { status: 'gather_failure', status_reason: 'Failed to parse PDB data.', raw_output: point.raw_output }
        }

        const pdb_count: number = parsed.pdb_count ?? 0

        if (pdb_count === 0) {
            return {
                status: 'warning',
                status_reason: 'No Pod Disruption Budgets found in the Wire namespace.',
                fix_hint: 'Create PDBs for critical services:\n```yaml\napiVersion: policy/v1\nkind: PodDisruptionBudget\nmetadata:\n  name: brig-pdb\nspec:\n  minAvailable: 1\n  selector:\n    matchLabels:\n      app: brig\n```',
                display_value: '0 PDBs',
                raw_output: point.raw_output,
            }
        }

        // Check for PDBs with zero disruptions allowed (too aggressive)
        const zero_allowed: number = (parsed.pdbs ?? []).filter(
            (p: { disruptions_allowed: number }) => p.disruptions_allowed === 0
        ).length

        if (zero_allowed > 0) {
            const names: string = (parsed.pdbs ?? [])
                .filter((p: { disruptions_allowed: number }) => p.disruptions_allowed === 0)
                .map((p: { name: string }) => `**${p.name}**`)
                .join(', ')

            return {
                status: 'warning',
                status_reason: '{{zero_allowed}} PDB(s) currently allow zero disruptions: {{{names}}}. Node drains will be blocked.',
                fix_hint: 'PDBs with zero allowed disruptions block node drains entirely. This usually means too few healthy pods relative to the PDB minimum. Scale up replicas or adjust the PDB.',
                display_value: `${pdb_count} PDBs, ${zero_allowed} blocking`,
                raw_output: point.raw_output,
                template_data: { zero_allowed, names },
            }
        }

        return {
            status: 'healthy',
            status_reason: '{{pdb_count}} Pod Disruption Budget(s) configured and allowing disruptions.',
            display_value: `${pdb_count} PDBs`,
            raw_output: point.raw_output,
            template_data: { pdb_count },
        }
    }
}

export default DisruptionBudgetsChecker
