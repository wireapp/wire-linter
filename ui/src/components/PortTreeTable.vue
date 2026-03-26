<!--
    PortTreeTable.vue - Three-level tree for port connectivity results.

    Source → target → port hierarchy with expand/collapse at each level.
    Non-open ports can show a detail panel with firewall analysis and fixes.

    Extracted from PortsTab to separate rendering from view orchestration.

    Props:
      tree_data         - SourceGroup[] from use_port_data
      firewall_data_map - Map<string, FirewallData> for details
-->
<template>
    <div class="results-tree ports-tree" style="margin-top: 12px;">
        <div class="tree-header">
            <span class="port-col-source">Source</span>
            <span class="port-col-target">Target</span>
            <span class="port-col-port">Port</span>
            <span class="port-col-service">Service</span>
            <span class="port-col-status">Status</span>
            <span class="port-col-action"></span>
        </div>

        <div v-for="source_group in tree_data" :key="source_group.key" class="tree-group">
            <div class="tree-row tree-row-group" @click="toggle_source(source_group.key)">
                <span class="port-col-source">
                    <i class="pi" :class="expanded_sources[source_group.key] ? 'pi-chevron-down' : 'pi-chevron-right'" style="font-size: 11px; margin-right: 6px;"></i>
                    <i class="pi pi-server" style="margin-right: 6px; color: var(--wire-blue);"></i>
                    <span class="group-label">{{ source_group.name }}</span>
                </span>
                <span class="port-col-target"></span>
                <span class="port-col-port"></span>
                <span class="port-col-service"></span>
                <span class="port-col-status">
                    <span class="group-summary">{{ source_group.open }}/{{ source_group.total }} open</span>
                </span>
                <span class="port-col-action"></span>
            </div>

            <template v-if="expanded_sources[source_group.key]">
                <div v-for="target_group in source_group.targets" :key="target_group.key" class="tree-subgroup">
                    <div class="tree-row tree-row-subgroup" @click="toggle_target(target_group.key)" style="padding-left: 32px;">
                        <span class="port-col-source"></span>
                        <span class="port-col-target">
                            <i class="pi" :class="expanded_targets[target_group.key] ? 'pi-chevron-down' : 'pi-chevron-right'" style="font-size: 11px; margin-right: 6px;"></i>
                            <i class="pi pi-database" style="margin-right: 6px; color: var(--wire-orange);"></i>
                            <span class="group-label">{{ target_group.name }}</span>
                        </span>
                        <span class="port-col-port"></span>
                        <span class="port-col-service"></span>
                        <span class="port-col-status">
                            <span class="group-summary">{{ target_group.open }}/{{ target_group.total }} open</span>
                        </span>
                        <span class="port-col-action"></span>
                    </div>

                    <template v-if="expanded_targets[target_group.key]">
                        <div v-for="port_row in target_group.ports" :key="port_row.id">
                            <div class="tree-row tree-row-leaf" style="padding-left: 64px;">
                                <span class="port-col-source"></span>
                                <span class="port-col-target"></span>
                                <span class="port-col-port">
                                    <span class="value-cell">{{ port_row.port }}/{{ port_row.protocol }}</span>
                                </span>
                                <span class="port-col-service">{{ port_row.service }}</span>
                                <span class="port-col-status">
                                    <span class="port-status-badge" :class="'port-status-' + port_row.status">
                                        {{ port_row.status }}
                                    </span>
                                </span>
                                <span class="port-col-action">
                                    <button
                                        v-if="port_row.status !== 'open'"
                                        class="details-toggle"
                                        :class="{ active: open_details[port_row.id] }"
                                        @click="toggle_detail(port_row.id)"
                                    >
                                        <i class="pi pi-wrench"></i>
                                        <span>{{ open_details[port_row.id] ? 'Hide' : 'Fix' }}</span>
                                    </button>
                                </span>
                            </div>

                            <PortRowDetail
                                v-if="open_details[port_row.id]"
                                :port_row="port_row"
                                :firewall_data_map="firewall_data_map"
                                @close="toggle_detail(port_row.id)"
                            />
                        </div>
                    </template>
                </div>
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, watch } from 'vue'

// Ours
import type { SourceGroup, FirewallData } from '../lib/port_types'
import PortRowDetail from './PortRowDetail.vue'

// -- Props --

const props = defineProps<{
    tree_data: SourceGroup[]
    firewall_data_map: Map<string, FirewallData>
}>()

// -- Expand/collapse state --

const expanded_sources = ref<Record<string, boolean>>({})
const expanded_targets = ref<Record<string, boolean>>({})
const open_details = ref<Record<string, boolean>>({})

// Keys the user has manually toggled — these survive watcher re-runs
// so that auto-expand logic doesn't override deliberate user actions.
const user_toggled_sources = new Set<string>()
const user_toggled_targets = new Set<string>()

// Auto-expand source groups with issues whenever tree_data changes so
// users can immediately see which ports need attention without manual clicks.
// Preserves expansion state for keys the user has manually toggled.
watch(() => props.tree_data, (groups) => {
    // Collect all valid keys from current data
    const valid_source_keys = new Set<string>()
    const valid_target_keys = new Set<string>()
    const valid_detail_ids = new Set<string>()

    for (const source of groups) {
        valid_source_keys.add(source.key)
        for (const target of source.targets) {
            valid_target_keys.add(target.key)
            for (const port of target.ports) {
                valid_detail_ids.add(port.id)
            }
        }
    }

    // Purge stale keys that no longer exist in the data
    for (const key of Object.keys(expanded_sources.value)) {
        if (!valid_source_keys.has(key)) {
            delete expanded_sources.value[key]
            user_toggled_sources.delete(key)
        }
    }
    for (const key of Object.keys(expanded_targets.value)) {
        if (!valid_target_keys.has(key)) {
            delete expanded_targets.value[key]
            user_toggled_targets.delete(key)
        }
    }
    for (const key of Object.keys(open_details.value)) {
        if (!valid_detail_ids.has(key)) {
            delete open_details.value[key]
        }
    }

    if (!groups.length) return

    // Auto-expand groups with issues, but only for keys the user hasn't touched
    for (const source of groups) {
        if (!user_toggled_sources.has(source.key)) {
            const has_issues = source.open < source.total
            expanded_sources.value[source.key] = has_issues
        }

        for (const target of source.targets) {
            if (!user_toggled_targets.has(target.key)) {
                expanded_targets.value[target.key] = target.open < target.total
            }
        }
    }

    // If no source was auto-expanded (everything healthy), expand all untouched sources
    const any_expanded = Object.values(expanded_sources.value).some(Boolean)
    if (!any_expanded) {
        for (const source of groups) {
            if (!user_toggled_sources.has(source.key)) {
                expanded_sources.value[source.key] = true
            }
        }
    }
}, { immediate: true })

// -- Toggle functions --

function toggle_source(key: string): void {
    user_toggled_sources.add(key)
    expanded_sources.value[key] = !expanded_sources.value[key]
}

function toggle_target(key: string): void {
    user_toggled_targets.add(key)
    expanded_targets.value[key] = !expanded_targets.value[key]
}

function toggle_detail(id: string): void {
    open_details.value[id] = !open_details.value[id]
}
</script>

<style scoped>
/* column widths */
.port-col-source  { flex: 0 0 22%; min-width: 0; display: flex; align-items: center; }
.port-col-target  { flex: 0 0 22%; min-width: 0; display: flex; align-items: center; }
.port-col-port    { flex: 0 0 12%; min-width: 0; }
.port-col-service { flex: 0 0 20%; min-width: 0; }
.port-col-status  { flex: 0 0 12%; min-width: 0; }
.port-col-action  { flex: 0 0 80px; display: flex; justify-content: flex-end; align-items: center; }

/* status badges */
.port-status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.port-status-open {
    background: #dcfce7;
    color: #166534;
}

.port-status-closed {
    background: #fee2e2;
    color: #991b1b;
}

.port-status-filtered {
    background: #fef3c7;
    color: #92400e;
}

.port-status-error {
    background: var(--wire-light-gray);
    color: var(--wire-medium-gray);
}
</style>
