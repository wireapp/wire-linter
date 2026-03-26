<!--
    ReportStep.vue - Step 6 of the Wire Fact Gathering wizard.

    Four tabs: Report (check results), Data (raw data points), Ports (diagrams),
    Config (gathering settings from the JSONL header).

    Owns tab selection, tree expand/collapse state, open panels, and PDF download.

    Props:
      - results:          CheckOutput[]          - analyzed check results
      - data_points_list: DataPoint[]            - raw collected data
      - gathering_config: GatheringConfig | null - config from JSONL header

    Emits:
      - 'back' → go back to step 5
-->
<template>
    <div class="step-content results-step">
        <h1 class="step-title">Fact Gathering Report</h1>
        <p class="step-description">
            Health analysis and raw collected data from your Wire backend.
            Switch between the <strong>Report</strong> tab for check results and the
            <strong>Data</strong> tab to browse every collected data point.
        </p>

        <div class="report-tabs">
            <button class="report-tab" :class="{ active: report_tab === 'report' }" @click="report_tab = 'report'">
                <i class="pi pi-list-check"></i>
                Report
                <span class="report-tab-badge">{{ results.length }}</span>
            </button>
            <button class="report-tab" :class="{ active: report_tab === 'data' }" @click="report_tab = 'data'">
                <i class="pi pi-database"></i>
                Raw Data
                <span class="report-tab-badge">{{ data_points_list.length }}</span>
            </button>
            <button class="report-tab" :class="{ active: report_tab === 'ports' }" @click="report_tab = 'ports'">
                <i class="pi pi-link"></i>
                Ports
            </button>
            <button class="report-tab" :class="{ active: report_tab === 'config' }" @click="report_tab = 'config'">
                <i class="pi pi-cog"></i>
                Config
            </button>
        </div>

        <div v-if="report_tab === 'report'">
            <CheckResultsTree
                :results="results"
                :tree_nodes="tree_nodes"
                v-model:expanded_keys="expanded_keys"
                v-model:open_panel="open_panel"
            />
        </div>

        <div v-if="report_tab === 'data'">
            <DataPointsTree
                :data_points_list="data_points_list"
                :data_tree_nodes="data_tree_nodes"
                v-model:data_expanded_keys="data_expanded_keys"
            />
        </div>

        <div v-if="report_tab === 'ports'">
            <PortsTab :data_points="data_points_list" />
        </div>

        <div v-if="report_tab === 'config'">
            <ConfigTab :config="gathering_config" />
        </div>

        <div class="step-actions">
            <Button label="Back" severity="secondary" icon="pi pi-arrow-left" @click="$emit('back')" />
            <Button label="Download Report" icon="pi pi-download" @click="handle_download_report" />
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, computed } from 'vue'
import Button from 'primevue/button'

// Ours
import PortsTab from './PortsTab.vue'
import ConfigTab from './ConfigTab.vue'
import CheckResultsTree from './CheckResultsTree.vue'
import DataPointsTree from './DataPointsTree.vue'
import { download_report } from '../lib/report_pdf'
import { use_result_trees } from '../composables/use_result_trees'
import type { CheckOutput } from '../checkers/base_checker'
import type { DataPoint, GatheringConfig } from '../sample-data'

// -- Props & Emits --

const props = defineProps<{
    results: CheckOutput[]
    data_points_list: DataPoint[]
    gathering_config: GatheringConfig | null
}>()

defineEmits<{
    (e: 'back'): void
}>()

// -- State --

const report_tab = ref<'report' | 'data' | 'ports' | 'config'>('report')
const expanded_keys = ref<Record<string, boolean>>({})
const open_panel = ref<Record<string, string>>({})
const data_expanded_keys = ref<Record<string, boolean>>({})

// -- Tree builders (composable) --

const results_ref = computed(() => props.results)
const data_points_ref = computed(() => props.data_points_list)
const { tree_nodes, data_tree_nodes, expand_all_tree_nodes } = use_result_trees(results_ref, data_points_ref)

// -- Methods --

async function handle_download_report(): Promise<void> {
    await download_report(props.results, props.data_points_list)
}

// expand all trees to default state. called by parent after setting new results.
function expand_all(): void {
    const { keys, data_keys } = expand_all_tree_nodes()
    expanded_keys.value      = keys
    data_expanded_keys.value = data_keys

    open_panel.value      = {}
}

defineExpose({ expand_all })
</script>

<style scoped>
/* report tab switcher */
.report-tabs {
    display: flex;
    gap: 0;
    margin-bottom: 24px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    overflow: hidden;
    width: fit-content;
}

.report-tab {
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    background: var(--wire-white);
    color: var(--wire-medium-gray);
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.2s;
}

.report-tab:not(:last-child) {
    border-right: 1px solid var(--wire-border-gray);
}

.report-tab.active {
    background: var(--wire-blue);
    color: white;
}

.report-tab:not(.active):hover {
    background: var(--wire-light-gray);
}

/* item count badge in tabs */
.report-tab-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(0, 0, 0, 0.10);
    line-height: 1;
}

.report-tab.active .report-tab-badge {
    background: rgba(255, 255, 255, 0.25);
}
</style>
