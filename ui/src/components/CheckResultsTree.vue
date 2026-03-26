<!-- CheckResultsTree.vue - Check results tree with hierarchical group/subgroup/leaf
     rows, inline details panels, and configmap panels.

     Extracted from App.vue's Report tab to reduce template complexity and co-locate
     the tree's template with its specific styles. The tree displays checker results
     grouped by category, with expand/collapse navigation and inline detail views.
     Summary cards are rendered by the child SummaryCards component.

     Props:
       results      - flat CheckOutput[] forwarded to SummaryCards for counts
       tree_nodes   - pre-built category to checker tree nodes

     v-model:
       expanded_keys - Record<string, boolean> tracking which groups are expanded
       open_panel    - Record<string, string> tracking which leaf panel is open ('details' | 'configmap' | '')
-->
<template>
    <!-- Summary cards showing count breakdown by status -->
    <SummaryCards :results="results" />

    <!-- Hierarchical results tree with groups, subgroups, and leaf rows -->
    <div class="results-tree" style="margin-top: 24px;">
        <!-- Header row -->
        <div class="tree-header">
            <span class="tree-col-check">Check</span>
            <span class="tree-col-value">Value</span>
            <span class="tree-col-status">Status</span>
            <span class="tree-col-rec">Recommendation</span>
            <span class="tree-col-action"></span>
        </div>

        <!-- Top-level groups -->
        <div v-for="group in tree_nodes" :key="group.key" class="tree-group">
            <!-- Group header -->
            <div class="tree-row tree-row-group" @click="toggle_group(group.key)">
                <span class="tree-col-check">
                    <i class="pi" :class="expanded_keys[group.key] ? 'pi-chevron-down' : 'pi-chevron-right'" style="font-size: 11px; margin-right: 6px;"></i>
                    <span class="group-label">{{ group.data.name }}</span>
                </span>
                <span class="tree-col-value">
                    <span class="group-summary">{{ group.data.child_summary }}</span>
                </span>
                <span class="tree-col-status">
                    <span class="status-badge" :class="group.data.worst_status">
                        <i :class="status_icon(group.data.worst_status)"></i>
                        {{ status_label(group.data.worst_status) }}
                    </span>
                </span>
                <span class="tree-col-rec"></span>
                <span class="tree-col-action"></span>
            </div>

            <!-- Children - sub-groups or leaves -->
            <template v-if="expanded_keys[group.key]">
                <template v-for="child in group.children" :key="child.key">
                    <!-- Sub-group -->
                    <template v-if="!child.data.is_leaf">
                        <div class="tree-row tree-row-subgroup" @click="toggle_group(child.key)">
                            <span class="tree-col-check" style="padding-left: 28px;">
                                <i class="pi" :class="expanded_keys[child.key] ? 'pi-chevron-down' : 'pi-chevron-right'" style="font-size: 10px; margin-right: 6px;"></i>
                                <span class="group-label">{{ child.data.name }}</span>
                            </span>
                            <span class="tree-col-value">
                                <span class="group-summary">{{ as_group(child).data.child_summary }}</span>
                            </span>
                            <span class="tree-col-status">
                                <span class="status-badge" :class="as_group(child).data.worst_status">
                                    <i :class="status_icon(as_group(child).data.worst_status)"></i>
                                    {{ status_label(as_group(child).data.worst_status) }}
                                </span>
                            </span>
                            <span class="tree-col-rec"></span>
                            <span class="tree-col-action"></span>
                        </div>

                        <!-- Sub-group leaves -->
                        <template v-if="expanded_keys[child.key]">
                            <CheckResultLeafRow
                                v-for="leaf in as_group(child).children" :key="leaf.key"
                                :node="as_leaf(leaf)" :indent_px="52" v-model:open_panel="open_panel"
                            />
                        </template>
                    </template>

                    <!-- Direct leaf without a sub-group -->
                    <template v-else>
                        <CheckResultLeafRow
                            :node="as_leaf(child)" :indent_px="28" v-model:open_panel="open_panel"
                        />
                    </template>
                </template>
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
// External no vue imports needed; SummaryCards handles its own computed counts

// Ours
import type { CheckOutput } from '../checkers/base_checker'
import type { CheckTreeGroupNode, CheckTreeLeafNode, CheckTreeNode } from '../composables/use_result_trees'
import { status_icon, status_label } from '../lib/format_utils'
import CheckResultLeafRow from './CheckResultLeafRow.vue'
import SummaryCards from './SummaryCards.vue'

// -- Props --

const props = defineProps<{
    // Flat list of checker outputs, used for computing summary card counts
    results: CheckOutput[]
    // Pre-built category to checker tree nodes from use_result_trees composable
    tree_nodes: CheckTreeGroupNode[]
}>()

// -- Two-way bindings for parent-managed expand/panel state --

// Which tree groups are expanded (keyed by node key)
const expanded_keys = defineModel<Record<string, boolean>>('expanded_keys', { required: true })

// Which leaf panel is open 'details', 'configmap', or '' (none)
const open_panel = defineModel<Record<string, string>>('open_panel', { required: true })

// -- Type narrowing helpers --

// Narrows a union CheckTreeNode to its group variant for type-safe template access
function as_group(node: CheckTreeNode): CheckTreeGroupNode {
    return node as CheckTreeGroupNode
}

// Narrows a union CheckTreeNode to its leaf variant for type-safe template access
function as_leaf(node: CheckTreeNode): CheckTreeLeafNode {
    return node as CheckTreeLeafNode
}

// -- Local toggle methods --

function toggle_group(key: string) {
    // Guard against undefined in case parent omits the required prop at runtime
    if (!expanded_keys.value) return
    expanded_keys.value[key] = !expanded_keys.value[key]
}

</script>

<style scoped>
/* Check tree column widths */

.tree-col-check  { flex: 0 0 28%; min-width: 0; display: flex; align-items: center; }
.tree-col-value  { flex: 0 0 16%; min-width: 0; }
.tree-col-status { flex: 0 0 12%; min-width: 0; }
.tree-col-rec    { flex: 1; min-width: 0; }
.tree-col-action { flex: 0 0 170px; display: flex; gap: 4px; justify-content: flex-end; align-items: center; flex-wrap: wrap; }

</style>
