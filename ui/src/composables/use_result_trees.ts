// use_result_trees.ts transforms flat CheckOutput[] and DataPoint[] lists into
// hierarchical tree structures for PrimeVue TreeTable components.
//
// Returns computed tree_nodes (category + checker tree) and data_tree_nodes (trie-based
// path tree), plus expand_all_tree_nodes() helper. Also exports build_status_summary,
// get_worst_status, and format_segment for testing/reuse.

// External
import { computed, type Ref } from 'vue'

// Ours
import type { CheckOutput, CheckStatus } from '../checkers/base_checker'
import type { DataPoint } from '../sample-data'

// ── Check tree node types (used by CheckResultsTree component) ───────────────

// Leaf node data — one checker result within a category group
export interface CheckTreeLeafData {
    name:              string
    path:              string
    description:       string
    value:             string | number | boolean | undefined
    unit:              string | undefined
    status:            CheckStatus
    status_reason:     string
    recommendation:    string
    raw_output:        string | null
    configmap_data:    string
    explanation:       string
    fix_hint:          string
    commands:          string[]
    collected_at:      string
    duration_seconds:  number | undefined
    gathered_from:     string
    data_points_used:  DataPoint[]
    template_data:     Record<string, unknown>
    is_leaf:           true
}

// Group node data — category header aggregating multiple checkers
export interface CheckTreeGroupData {
    name:           string
    worst_status:   CheckStatus
    child_summary:  string
    is_leaf:        false
}

// Leaf node in the check tree
export interface CheckTreeLeafNode {
    key:  string
    data: CheckTreeLeafData
}

// Group node in the check tree (children can be leaves or nested sub-groups)
export interface CheckTreeGroupNode {
    key:      string
    data:     CheckTreeGroupData
    children: CheckTreeNode[]
}

// Either a leaf or a group in the check tree
export type CheckTreeNode = CheckTreeLeafNode | CheckTreeGroupNode

// ── Trie node used during data-tree construction ──────────────────────────────

export interface TrieNode {
    children: Map<string, TrieNode>
    dp?: DataPoint
}

// ── Data tree node types (used by DataPointsTree component) ───────────────────

// Leaf node actual collected data point
export interface DataTreeNodeLeafData {
    is_leaf:           true
    name:              string
    full_path:         string
    value:             string | number | boolean | null
    unit:              string
    description:       string
    raw_output?:       string
    collected_at?:     string
    duration_seconds?: number
    health_info?:      string
    error?:            string
    commands:          string[]
    json_source:       string
    // Original DataPoint reference for the DataPointRow component
    source_dp:         DataPoint
}

// Group/folder node category or sub-category
export interface DataTreeNodeGroupData {
    is_leaf:     false
    name:        string
    full_path:   string
    child_count: number
}

// Leaf in the data tree actual data point
export interface DataTreeLeafNode {
    key:  string
    data: DataTreeNodeLeafData
}

// Group in the data tree category or sub-category
export interface DataTreeGroupNode {
    key:      string
    data:     DataTreeNodeGroupData
    children: DataTreeNode[]
}

// Either a leaf or a group
export type DataTreeNode = DataTreeLeafNode | DataTreeGroupNode

// Check if node is a leaf
export function is_leaf_node(node: DataTreeNode): node is DataTreeLeafNode {
    return node.data.is_leaf === true
}

// Check if node is a group
export function is_group_node(node: DataTreeNode): node is DataTreeGroupNode {
    return node.data.is_leaf === false
}

// ── Helper functions ──────────────────────────────────────────────────────────

// Build a status summary string. e.g. « 2 unhealthy, 1 warning, 5 healthy »
export function build_status_summary(items: CheckOutput[]): string {
    const unhealthy       = items.filter((r) => r.status === 'unhealthy').length
    const warning         = items.filter((r) => r.status === 'warning').length
    const gather_failure  = items.filter((r) => (r.status as CheckStatus) === 'gather_failure').length
    const healthy         = items.filter((r) => r.status === 'healthy').length
    const not_applicable  = items.filter((r) => (r.status as CheckStatus) === 'not_applicable').length
    const parts: string[] = []
    if (unhealthy > 0)       parts.push(`${unhealthy} unhealthy`)
    if (warning > 0)         parts.push(`${warning} warning`)
    if (gather_failure > 0)  parts.push(`${gather_failure} gather failure`)
    if (healthy > 0)         parts.push(`${healthy} healthy`)
    if (not_applicable > 0)  parts.push(`${not_applicable} not tested`)
    return parts.join(', ')
}

// Find the worst status. Skip not_applicable and gather_failure since they
// just mean the check was skipped or data was missing, not that something's broken.
export function get_worst_status(items: CheckOutput[]): CheckStatus {
    // Filter out meta-statuses that don't indicate actual failures
    const real = items.filter((r) => {
        const s = r.status as CheckStatus
        return s !== 'not_applicable' && s !== 'gather_failure'
    })
    if (real.length === 0) {
        // No real checks. Show gather_failure if it exists, otherwise not_applicable.
        if (items.some((r) => (r.status as CheckStatus) === 'gather_failure')) return 'gather_failure'
        return 'not_applicable'
    }
    if (real.some((r) => r.status === 'unhealthy')) return 'unhealthy'
    if (real.some((r) => r.status === 'warning')) return 'warning'
    return 'healthy'
}

// Format path segment to title case. « cluster_status » becomes « Cluster Status »
export function format_segment(segment: string): string {
    return segment
        .replace(/[_-]/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
}

// ── Composable ────────────────────────────────────────────────────────────────

// Build reactive trees from flat results and data points.
export function use_result_trees(
    results: Ref<CheckOutput[]>,
    data_points_list: Ref<DataPoint[]>,
) {
    // Group checks by category
    const tree_nodes = computed(() => {
        const category_groups: Record<string, CheckOutput[]> = {}

        for (const result of results.value) {
            if (!category_groups[result.category]) category_groups[result.category] = []
            category_groups[result.category]!.push(result)
        }

        const nodes: CheckTreeGroupNode[] = []
        let node_key = 0

        // Sort categories alphabetically
        const sorted_categories = Object.keys(category_groups).sort()

        for (const category of sorted_categories) {
            const category_results = category_groups[category]!
            const worst = get_worst_status(category_results)
            const child_summary = build_status_summary(category_results)
            const parent_key = String(node_key++)

            // Each checker in the category becomes a direct leaf node
            const children = category_results.map((result) => ({
                key: String(node_key++),
                data: {
                    name: result.name,
                    path: result.path,
                    description: result.name,
                    value: result.display_value,
                    unit: result.display_unit,
                    status: result.status,
                    // What we found — explains why we arrived at this verdict.
                    // Already rendered by registry.ts after checker execution.
                    status_reason: result.status_reason,
                    // How to fix this — actionable steps (Markdown, present for non-healthy)
                    fix_hint: result.fix_hint ?? '',
                    recommendation: result.recommendation || '',
                    // null = no raw_output, empty = target ran with no stdout
                    raw_output: result.raw_output ?? null,
                    // Extracted service config for ConfigMap display
                    configmap_data: result.configmap_data || '',
                    // Why this check exists — always present, from the checker class
                    explanation:      result.explanation,
                    // Actionable remediation steps — already rendered by registry.ts
                    fix_hint:         result.fix_hint ?? '',
                    // Collection context from the primary DataPoint
                    commands:         result.commands         ?? [],
                    collected_at:     result.collected_at     ?? '',
                    duration_seconds: result.duration_seconds,
                    gathered_from:    result.gathered_from    ?? '',
                    // DataPoints accessed by this checker
                    data_points_used: result.data_points_used ?? [],
                    // Key-value context for Handlebars template rendering
                    template_data:    result.template_data ?? {},
                    is_leaf: true as const,
                },
            }))

            nodes.push({
                key: parent_key,
                data: {
                    name: category,
                    worst_status: worst,
                    child_summary: child_summary,
                    is_leaf: false as const,
                },
                children,
            })
        }

        return nodes
    })

    // Build tree from flat DataPoint list, split paths on '/'.
    const data_tree_nodes = computed(() => {
        const root: TrieNode = { children: new Map() }

        // Insert every data point into the trie using its path segments
        for (const dp of data_points_list.value) {
            const segments = dp.path.split('/')
            let node = root
            for (const seg of segments) {
                if (!node.children.has(seg)) {
                    node.children.set(seg, { children: new Map() })
                }
                node = node.children.get(seg)!
            }
            node.dp = dp
        }

        let key_counter = 0

        // Count leaf nodes in a subtree
        function count_dp_leaves(nodes: DataTreeNode[]): number {
            let total = 0
            for (const n of nodes) {
                if (is_leaf_node(n)) total++
                else total += count_dp_leaves(n.children)
            }
            return total
        }

        // Convert trie node to display node
        function build_node(trie_node: TrieNode, segment: string, parent_path = ''): DataTreeNode {
            const key = String(key_counter++)
            const has_children = trie_node.children.size > 0

            if (!has_children && trie_node.dp) {
                // Single data point leaf
                const dp = trie_node.dp
                // Metadata-only JSON view (raw_output shown separately)
                const { raw_output, ...dp_meta } = dp
                return {
                    key,
                    data: {
                        is_leaf:          true,
                        name:             format_segment(segment),
                        full_path:        dp.path,
                        value:            dp.value,
                        unit:             dp.unit ?? '',
                        description:      dp.description,
                        raw_output:       raw_output,
                        collected_at:     dp.metadata?.collected_at,
                        duration_seconds: dp.metadata?.duration_seconds,
                        health_info:      dp.metadata?.health_info,
                        error:            dp.metadata?.error,
                        commands:         dp.metadata?.commands ?? [],
                        json_source:      JSON.stringify(dp_meta, null, 2),
                        source_dp:        dp,
                    },
                }
            }

            // Recurse into children, passing the accumulated path so group nodes get full_path
            const full_path = parent_path ? `${parent_path}/${segment}` : segment
            const children = Array.from(trie_node.children.entries())
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([seg, child]) => build_node(child, seg, full_path))

            // If this node is both a group AND has a dp, inject it as a leaf first.
            // (path is a prefix of another data-point path)
            if (trie_node.dp) {
                const dp = trie_node.dp
                const { raw_output, ...dp_meta } = dp
                children.unshift({
                    key: String(key_counter++),
                    data: {
                        is_leaf:          true,
                        name:             format_segment(segment),
                        full_path:        dp.path,
                        value:            dp.value,
                        unit:             dp.unit ?? '',
                        description:      dp.description,
                        raw_output:       raw_output,
                        collected_at:     dp.metadata?.collected_at,
                        duration_seconds: dp.metadata?.duration_seconds,
                        health_info:      dp.metadata?.health_info,
                        error:            dp.metadata?.error,
                        commands:         dp.metadata?.commands ?? [],
                        json_source:      JSON.stringify(dp_meta, null, 2),
                        source_dp:        dp,
                    },
                })
            }

            return {
                key,
                data: {
                    is_leaf:     false,
                    name:        format_segment(segment),
                    full_path:   full_path,
                    child_count: count_dp_leaves(children),
                },
                children,
            }
        }

        // Return sorted top-level groups
        return Array.from(root.children.entries())
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([seg, child]) => build_node(child, seg))
    })

    // Compute default expanded keys for both trees
    function expand_all_tree_nodes(): {
        keys:      Record<string, boolean>
        data_keys: Record<string, boolean>
    } {
        // Expand all category groups and any sub-groups with children
        const keys: Record<string, boolean> = {}
        for (const node of tree_nodes.value) {
            keys[node.key] = true
            for (const child of node.children) {
                // Sub-groups (non-leaf children) should also be expanded
                if (!child.data.is_leaf) keys[child.key] = true
            }
        }

        // Expand only top-level data tree groups
        const data_keys: Record<string, boolean> = {}
        for (const node of data_tree_nodes.value) {
            data_keys[node.key] = true
        }

        return { keys, data_keys }
    }

    return {
        tree_nodes,
        data_tree_nodes,
        expand_all_tree_nodes,
    }
}
