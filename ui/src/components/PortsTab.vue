<template>
    <div class="ports-tab">
        <div v-if="port_results.length > 0" class="ports-view-tabs">
            <button class="ports-view-tab" :class="{ active: view_mode === 'table' }" @click="view_mode = 'table'">
                <i class="pi pi-list"></i>
                Table
                <span class="ports-view-badge">{{ total_port_count }}</span>
            </button>
            <button class="ports-view-tab" :class="{ active: view_mode === 'diagram' }" @click="view_mode = 'diagram'">
                <i class="pi pi-sitemap"></i>
                Diagram
                <span class="ports-view-badge">{{ unique_nodes.length }}</span>
            </button>
        </div>

        <div v-if="port_results.length === 0" class="ports-empty">
            <i class="pi pi-info-circle" style="font-size: 24px; color: var(--wire-medium-gray);"></i>
            <p>No port connectivity data found.</p>
            <p class="ports-empty-hint">
                Run the gatherer with the <code>port_connectivity</code> target enabled to collect inter-node port test results.
            </p>
        </div>

        <template v-if="view_mode === 'table' && port_results.length > 0">
            <div class="ports-summary-row">
                <span class="ports-summary-item ports-summary-total">
                    <i class="pi pi-link"></i>
                    {{ total_port_count }} ports tested
                </span>
                <span class="ports-summary-item ports-summary-open">
                    {{ open_count }} open
                </span>
                <span v-if="closed_count > 0" class="ports-summary-item ports-summary-closed">
                    {{ closed_count }} closed
                </span>
                <span v-if="filtered_count > 0" class="ports-summary-item ports-summary-filtered">
                    {{ filtered_count }} filtered
                </span>
            </div>

            <PortTreeTable :tree_data="tree_data" :firewall_data_map="firewall_data_map" />
        </template>

        <template v-if="view_mode === 'diagram' && port_results.length > 0">
            <div
                v-for="entry in all_node_svgs"
                :key="entry.name"
                class="diagram-container"
                v-html="entry.svg"
            ></div>
        </template>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, toRef } from 'vue'

// Ours
import type { DataPoint } from '../sample-data'
import { use_port_diagrams } from '../composables/use_port_diagrams'
import PortTreeTable from './PortTreeTable.vue'
import { use_port_data } from '../composables/use_port_data'

// -- Props --

const props = defineProps<{
    data_points: DataPoint[]
}>()

// -- State --

const view_mode = ref<'table' | 'diagram'>('table')

// -- Data extraction --

const {
    port_results,
    firewall_data_map,
    total_port_count,
    open_count,
    closed_count,
    filtered_count,
    tree_data,
} = use_port_data(toRef(props, 'data_points'))

// -- Diagram --

const { unique_nodes, all_node_svgs } = use_port_diagrams(port_results)

</script>

<style scoped>
/* view switcher */
.ports-view-tabs {
    display: flex;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 16px;
}

.ports-view-tab {
    flex: 1;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    background: var(--wire-white);
    color: var(--wire-medium-gray);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: all 0.2s;
}

.ports-view-tab:not(:last-child) {
    border-right: 1px solid var(--wire-border-gray);
}

.ports-view-tab.active {
    background: var(--wire-blue);
    color: white;
}

.ports-view-tab:not(.active):hover {
    background: var(--wire-light-gray);
}

.ports-view-badge {
    font-size: 11px;
    padding: 1px 7px;
    border-radius: 9px;
    background: rgba(0, 0, 0, 0.08);
    font-weight: 600;
}

.ports-view-tab.active .ports-view-badge {
    background: rgba(255, 255, 255, 0.25);
    color: white;
}

/* empty state */
.ports-empty {
    text-align: center;
    padding: 48px 24px;
    color: var(--wire-medium-gray);
}

.ports-empty p {
    margin-top: 8px;
    font-size: 14px;
}

.ports-empty-hint {
    font-size: 13px !important;
    color: #999;
}

.ports-empty-hint code {
    background: var(--wire-light-gray);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
}

/* summary row */
.ports-summary-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 0;
    font-size: 13px;
}

.ports-summary-item {
    display: flex;
    align-items: center;
    gap: 4px;
}

.ports-summary-total {
    font-weight: 600;
    color: var(--wire-dark-gray);
}

.ports-summary-open {
    color: var(--wire-green);
    font-weight: 600;
}

.ports-summary-closed {
    color: var(--wire-red);
    font-weight: 600;
}

.ports-summary-filtered {
    color: var(--wire-orange);
    font-weight: 600;
}

/* diagram containers */
.diagram-container {
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    overflow: hidden;
    background: #f8fafc;
    margin-bottom: 24px;
}

.diagram-container:last-child {
    margin-bottom: 0;
}

.diagram-container :deep(svg) {
    width: 100%;
    height: auto;
}
</style>
