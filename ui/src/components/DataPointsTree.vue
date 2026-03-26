<!-- DataPointsTree.vue - Data points tree with summary row, hierarchical
     group/subgroup/leaf rows. Leaf rows are rendered by the DataPointRow
     component which self-manages its own expand/collapse detail panel.

     Extracted from App.vue's Data tab to reduce template complexity and co-locate
     the tree's template with its specific styles. The tree displays collected data
     points grouped by category/subcategory, with expand/collapse navigation.

     Props:
       data_points_list - flat DataPoint[] for computing the summary count
       data_tree_nodes  - pre-built category to data point tree nodes

     v-model:
       data_expanded_keys - Record<string, boolean> tracking which groups are expanded
-->
<template>
    <!-- Summary row showing total data point count -->
    <div class="data-summary-row">
        <span class="data-summary-text">
            <i class="pi pi-database"></i>
            {{ data_points_list.length }} data points collected across {{ data_tree_nodes.length }} categories
        </span>
    </div>

    <!-- Hierarchical data points tree with groups, subgroups, and leaf rows -->
    <div class="results-tree data-tree" style="margin-top: 12px;">
        <!-- Header row -->
        <div class="tree-header">
            <span class="data-col-name">Data Point</span>
            <span class="data-col-value">Value</span>
            <span class="data-col-desc">Description</span>
            <span class="data-col-meta">Collected</span>
            <span class="data-col-action"></span>
        </div>

        <!-- Top-level groups -->
        <div v-for="group in data_tree_nodes" :key="group.key" class="tree-group">
            <template v-if="is_group_node(group)">
            <!-- Group header -->
            <div class="tree-row tree-row-group" @click="toggle_group(group.key)">
                <span class="data-col-name">
                    <i class="pi" :class="data_expanded_keys[group.key] ? 'pi-chevron-down' : 'pi-chevron-right'" style="font-size: 11px; margin-right: 6px;"></i>
                    <i class="pi pi-folder data-folder-icon"></i>
                    <span class="group-label">{{ group.data.name }}</span>
                </span>
                <span class="data-col-value"></span>
                <span class="data-col-desc"><span class="group-summary">{{ group.data.child_count }} data point{{ group.data.child_count !== 1 ? 's' : '' }}</span></span>
                <span class="data-col-meta"></span>
                <span class="data-col-action"></span>
            </div>

            <!-- Children - sub-groups or leaves -->
            <template v-if="data_expanded_keys[group.key]">
                <template v-for="child in group.children" :key="child.key">

                    <!-- Sub-group -->
                    <template v-if="is_group_node(child)">
                        <div class="tree-row tree-row-subgroup" @click="toggle_group(child.key)">
                            <span class="data-col-name" style="padding-left: 28px;">
                                <i class="pi" :class="data_expanded_keys[child.key] ? 'pi-chevron-down' : 'pi-chevron-right'" style="font-size: 10px; margin-right: 6px;"></i>
                                <i class="pi pi-folder-open data-folder-icon" style="opacity: 0.7;"></i>
                                <span class="group-label">{{ child.data.name }}</span>
                            </span>
                            <span class="data-col-value"></span>
                            <span class="data-col-desc"><span class="group-summary">{{ child.data.child_count }} data point{{ child.data.child_count !== 1 ? 's' : '' }}</span></span>
                            <span class="data-col-meta"></span>
                            <span class="data-col-action"></span>
                        </div>

                        <!-- Sub-group leaves -->
                        <template v-if="data_expanded_keys[child.key]">
                            <template v-for="leaf in child.children" :key="leaf.key">
                                <template v-if="is_leaf_node(leaf)">
                                    <DataPointRow :data_point="leaf.data.source_dp" />
                                </template>
                            </template>
                        </template>
                    </template>

                    <!-- Direct leaf without a sub-group -->
                    <template v-else-if="is_leaf_node(child)">
                        <DataPointRow :data_point="child.data.source_dp" />
                    </template>

                </template>
            </template>
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
// Ours
import type { DataPoint } from '../sample-data'
import type { DataTreeNode } from '../composables/use_result_trees'
import { is_leaf_node, is_group_node } from '../composables/use_result_trees'
import DataPointRow from './DataPointRow.vue'

// -- Props --

const props = defineProps<{
    // Flat list of data points, used for computing the summary count
    data_points_list: DataPoint[]
    // Pre-built category to data point tree nodes from use_result_trees composable
    data_tree_nodes: DataTreeNode[]
}>()

// -- Two-way binding for parent-managed expand state --

// Which tree groups are expanded (keyed by node key)
const data_expanded_keys = defineModel<Record<string, boolean>>('data_expanded_keys', { required: true })

// -- Local toggle methods --

function toggle_group(key: string) {
    data_expanded_keys.value![key] = !data_expanded_keys.value![key]
}
</script>

<style scoped>
/* Tree header + group row columns — match DataPointRow's proportions so columns align */

.data-col-name   { flex: 0 0 30%; min-width: 0; display: flex; align-items: center; }
.data-col-value  { flex: 0 0 12%; min-width: 0; }
.data-col-desc   { flex: 1; min-width: 0; }
.data-col-meta   { flex: 0 0 110px; display: flex; flex-direction: column; gap: 3px; align-items: flex-end; }
.data-col-action { flex: 0 0 70px; display: flex; gap: 4px; justify-content: flex-end; align-items: center; }

/* Folder icon in data tree group rows */
.data-folder-icon {
    font-size: 12px;
    margin-right: 6px;
    color: var(--wire-blue);
}

/* Data summary row above the tree */

.data-summary-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 4px;
}

.data-summary-text {
    font-size: 13px;
    color: var(--wire-medium-gray);
    display: flex;
    align-items: center;
    gap: 6px;
}
</style>
