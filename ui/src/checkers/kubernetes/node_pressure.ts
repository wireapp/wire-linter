/**
 * Flags nodes under memory, disk, or PID pressure.
 *
 * A node can be Ready but still under pressure — triggering pod
 * evictions and degraded performance before going fully NotReady.
 *
 * Consumes: kubernetes/nodes/pressure_conditions
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class NodePressureChecker extends BaseChecker {
    readonly path: string = 'kubernetes/node_pressure'
    readonly name: string = 'Node pressure conditions'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly data_path: string = 'kubernetes/nodes/pressure_conditions'
    readonly explanation: string =
        'Nodes can report **Ready** but still have pressure conditions: **MemoryPressure** ' +
        'triggers pod evictions, **DiskPressure** prevents scheduling, **PIDPressure** means ' +
        'the node is running out of process IDs. These are early warnings before a node fails.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/nodes/pressure_conditions')

        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Node pressure data was not collected.',
                fix_hint: 'Re-run the gatherer with Kubernetes targets enabled.',
            }
        }

        let parsed: {
            total_nodes?: number
            nodes_with_pressure?: number
            details?: {
                name: string
                memory_pressure: boolean
                disk_pressure: boolean
                pid_pressure: boolean
                network_unavailable: boolean
                has_pressure: boolean
            }[]
        }
        try { parsed = JSON.parse(String(point.value)) } catch {
            return { status: 'gather_failure', status_reason: 'Failed to parse node pressure data.' }
        }

        // Guard against null/primitive results (e.g. point.value was null → JSON.parse("null") → null)
        if (parsed === null || typeof parsed !== 'object') {
            return { status: 'gather_failure', status_reason: 'Node pressure data is not a valid object.' }
        }

        const total: number = parsed.total_nodes ?? 0
        const under_pressure: number = parsed.nodes_with_pressure ?? 0

        if (total === 0) {
            return {
                status: 'gather_failure',
                status_reason: 'No nodes found in the cluster.',
            }
        }

        if (under_pressure > 0) {
            const pressure_details: string = (parsed.details ?? [])
                .filter((n: { has_pressure: boolean }) => n.has_pressure)
                .map((n: { name: string; memory_pressure: boolean; disk_pressure: boolean; pid_pressure: boolean; network_unavailable: boolean }) => {
                    const types: string[] = []
                    if (n.memory_pressure) types.push('Memory')
                    if (n.disk_pressure) types.push('Disk')
                    if (n.pid_pressure) types.push('PID')
                    if (n.network_unavailable) types.push('Network')
                    return `**${n.name}**: ${types.join(', ')} pressure`
                })
                .join('\n- ')

            return {
                status: 'unhealthy',
                status_reason: `**{{pressure_count}}** of {{total}} node(s) under pressure.`,
                fix_hint: '1. Check node status:\n   ```\n   kubectl describe node <node-name>\n   ```\n2. For MemoryPressure: reduce workloads or add memory\n3. For DiskPressure: clean up unused images (`crictl rmi --prune`) or expand storage\n4. For PIDPressure: investigate processes (`ps aux`) or increase pid_max',
                recommendation: `Nodes under pressure:\n- ${pressure_details}`,
                display_value: `${under_pressure} under pressure`,
                raw_output: point.raw_output,
                template_data: { pressure_count: under_pressure, total },
            }
        }

        return {
            status: 'healthy',
            status_reason: `No pressure conditions on any of ${total} node(s).`,
            display_value: `${total} OK`,
            raw_output: point.raw_output,
            template_data: { pressure_count: 0, total },
        }
    }
}

export default NodePressureChecker
