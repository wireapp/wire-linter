<!-- CheckResultLeafRow.vue - Single leaf row in the check-results tree, including
     the data row itself and the expandable details/configmap inline panels.

     Extracted from CheckResultsTree.vue to eliminate duplication - the leaf row
     template was duplicated verbatim for sub-group leaves (indented 52px) and
     direct leaves (indented 28px). This component unifies both via the indent_px prop.

     Props:
       node       - tree leaf node ({ key, data: { name, path, value, unit, status, ... } })
       indent_px  - left padding in pixels (controls visual nesting depth)

     v-model:
       open_panel - parent's panel state record ('details' | 'configmap' | '')
-->
<template>
    <!-- Data row with check, value, status, recommendation, and action columns -->
    <div class="tree-row tree-row-leaf">
        <span class="tree-col-check" :style="{ paddingLeft: indent_px + 'px' }">
            {{ node.data.name }}
        </span>
        <span class="tree-col-value">
            <span class="value-cell">{{ format_value(node.data.value, node.data.unit) }}</span>
        </span>
        <span class="tree-col-status">
            <span class="status-badge" :class="node.data.status">
                <i :class="status_icon(node.data.status)"></i>
                {{ status_label(node.data.status) }}
            </span>
        </span>
        <span class="tree-col-rec">
            <span v-if="node.data.recommendation" class="recommendation-text" v-html="render_markdown(node.data.recommendation)"></span>
            <span v-else class="recommendation-ok">No action needed</span>
        </span>
        <span class="tree-col-action">
            <button
                class="details-toggle"
                :class="{ active: open_panel[node.key] === 'details' }"
                @click="toggle_details"
            >
                <i class="pi pi-eye"></i>
                <span>{{ open_panel[node.key] === 'details' ? 'Hide' : 'Details' }}</span>
            </button>
            <button
                v-if="node.data.configmap_data || yaml_entries.length > 0"
                class="details-toggle configmap-toggle"
                :class="{ active: open_panel[node.key] === 'configmap' }"
                @click="toggle_configmap"
            >
                <i class="pi pi-file-edit"></i>
                <span>{{ open_panel[node.key] === 'configmap' ? 'Hide' : 'ConfigMap' }}</span>
            </button>
        </span>
    </div>

    <!-- Details panel with metadata and raw output -->
    <div v-if="open_panel[node.key] === 'details'" class="details-panel">
        <div class="details-panel-header">
            <div class="details-panel-title">
                <i class="pi pi-code"></i>
                <span>{{ node.data.path }}</span>
            </div>
            <div class="details-panel-meta">
                <span class="details-panel-desc">{{ node.data.description }}</span>
                <button class="details-close" @click="toggle_details"><i class="pi pi-times"></i></button>
            </div>
        </div>

        <!-- Collection context chips -->
        <div v-if="node.data.collected_at || node.data.gathered_from" class="details-context-bar">
            <span v-if="node.data.collected_at" class="context-chip">
                <i class="pi pi-clock"></i> {{ node.data.collected_at }}
            </span>
            <span v-if="node.data.duration_seconds != null" class="context-chip">
                <i class="pi pi-stopwatch"></i> {{ format_duration(node.data.duration_seconds, 1) }}s
            </span>
            <span v-if="node.data.gathered_from" class="context-chip">
                <i class="pi pi-map-marker"></i> {{ node.data.gathered_from }}
            </span>
        </div>

        <!-- Why this check exists — always present, from the checker class (Markdown) -->
        <div class="details-section">
            <div class="details-section-label">Why this check exists</div>
            <div class="details-section-text" v-html="render_markdown(node.data.explanation)"></div>
        </div>

        <!-- What we found — explains the reasoning behind the status verdict (Markdown) -->
        <div class="details-section">
            <div class="details-section-label">What we found</div>
            <div class="details-section-text details-finding" :class="'finding-' + node.data.status" v-html="render_markdown(node.data.status_reason)"></div>
        </div>

        <!-- Actionable remediation steps when the checker provides them -->
        <div v-if="node.data.fix_hint" class="details-section">
            <div class="details-section-label">How to fix</div>
            <div class="details-section-text details-fix-hint" v-html="render_markdown(node.data.fix_hint)"></div>
        </div>

        <!-- Commands that were executed to collect the primary data -->
        <div v-if="node.data.commands?.length > 0" class="details-section">
            <div class="details-section-label">Commands executed</div>
            <pre class="details-terminal details-commands">{{ node.data.commands.join('\n') }}</pre>
        </div>

        <!-- Raw command output -->
        <div class="details-section">
            <div class="details-section-label">Raw output</div>
            <pre v-if="node.data.raw_output" class="details-terminal" v-html="highlight_content(node.data.raw_output)"></pre>
            <div v-else-if="node.data.raw_output === ''" class="details-no-output">
                The target command ran but produced no output to display.
            </div>
            <div v-else class="details-no-output">
                Target data was not collected for this check. The scan may not have run this target, or it encountered an error before producing any output.
            </div>
        </div>

        <!-- Data points used by this checker -->
        <div v-if="node.data.data_points_used?.length > 0" class="details-section">
            <div class="details-section-label">
                Data points used ({{ node.data.data_points_used.length }})
            </div>
            <div class="dp-used-list">
                <DataPointRow
                    v-for="dp in node.data.data_points_used"
                    :key="dp.path"
                    :data_point="dp"
                    :compact="true"
                />
            </div>
        </div>
    </div>

    <!-- ConfigMap panel with extracted service config or YAML detected in JSON raw_output -->
    <div v-if="open_panel[node.key] === 'configmap'" class="details-panel configmap-panel">
        <div class="details-panel-header">
            <div class="details-panel-title">
                <i class="pi pi-file-edit"></i>
                <span>{{ node.data.path }} - ConfigMap data</span>
            </div>
            <div class="details-panel-meta">
                <span class="details-panel-desc">{{ node.data.description }}</span>
                <button class="details-close" @click="toggle_configmap"><i class="pi pi-times"></i></button>
            </div>
        </div>
        <pre v-if="node.data.configmap_data" class="details-terminal" v-html="highlight_content(node.data.configmap_data)"></pre>
        <template v-for="entry in yaml_entries" :key="entry.key">
            <div class="yaml-entry-label">{{ entry.key }}</div>
            <pre class="details-terminal" v-html="highlight_content(entry.content)"></pre>
        </template>
    </div>
</template>

<script setup lang="ts">
// External
import { computed } from 'vue'

// Ours
import { highlight_content, extract_yaml_entries_from_json } from '../lib/syntax_highlighter'
import { render_markdown } from '../lib/markdown_renderer'
import { format_value, format_duration, status_icon, status_label } from '../lib/format_utils'
import type { CheckTreeLeafNode } from '../composables/use_result_trees'
import DataPointRow from './DataPointRow.vue'

// -- Props --

const props = defineProps<{
    // The tree leaf node to render
    node: CheckTreeLeafNode
    // Left padding in pixels controls visual nesting depth
    indent_px: number
}>()

// Panel state record keyed by node key 'details' | 'configmap' | '' (none)
const open_panel = defineModel<Record<string, string>>('open_panel', { required: true })

// -- Lazy YAML extraction (only runs when configmap panel is open) --

// Extract YAML entries from raw_output JSON only when the user opens the configmap panel,
// avoiding ~126 unnecessary JSON.parse attempts on every tree rebuild
const yaml_entries = computed(() =>
    open_panel.value[props.node.key] === 'configmap'
        ? extract_yaml_entries_from_json(props.node.data.raw_output || '')
        : []
)

// -- Panel toggle methods --

function toggle_details(): void {
    open_panel.value[props.node.key] = open_panel.value[props.node.key] === 'details' ? '' : 'details'
}

function toggle_configmap(): void {
    open_panel.value[props.node.key] = open_panel.value[props.node.key] === 'configmap' ? '' : 'configmap'
}
</script>

<style scoped>
/* Check tree column widths (duplicated from parent - needed for scoped isolation) */

.tree-col-check  { flex: 0 0 28%; min-width: 0; display: flex; align-items: center; }
.tree-col-value  { flex: 0 0 16%; min-width: 0; }
.tree-col-status { flex: 0 0 12%; min-width: 0; }
.tree-col-rec    { flex: 1; min-width: 0; }
.tree-col-action { flex: 0 0 170px; display: flex; gap: 4px; justify-content: flex-end; align-items: center; flex-wrap: wrap; }

/* Recommendation text */

.recommendation-text {
    font-size: 12px;
    color: var(--wire-medium-gray);
    line-height: 1.4;
}

/* Shell command snippets embedded in recommendations (rendered as <code> by markdown) */
.recommendation-text :deep(code) {
    display: inline-block;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 11px;
    background-color: #1a1a1a;
    color: #ffffff;
    padding: 1px 6px;
    border-radius: 4px;
    white-space: pre;
    vertical-align: middle;
}

.recommendation-ok {
    font-size: 12px;
    color: #8fbc8f;
    font-style: italic;
}

/* Collection context chips below the header */

.details-context-bar {
    display: flex;
    gap: 10px;
    padding: 6px 16px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    flex-wrap: wrap;
}

.context-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #8a8a8a;
    background: rgba(255, 255, 255, 0.04);
    padding: 2px 8px;
    border-radius: 4px;
}

.context-chip i {
    font-size: 10px;
    color: #6b9bd2;
}

/* Details section labels and content */

.details-section {
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.details-section-label {
    padding: 8px 16px 4px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b9bd2;
}

.details-section-text {
    padding: 2px 16px 8px;
    font-size: 12px;
    line-height: 1.5;
    color: #c8c8c8;
}

/* Inline code from markdown rendering in explanation / status_reason sections */
.details-section-text :deep(code) {
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 11px;
    background-color: #1a1a1a;
    color: #e5c07b;
    padding: 1px 6px;
    border-radius: 4px;
}

/* "What we found" text — color-coded by status to reinforce the verdict */
.details-finding.finding-healthy       { color: #8fbc8f; }
.details-finding.finding-warning       { color: #e5c07b; }
.details-finding.finding-unhealthy     { color: #e06c75; }
.details-finding.finding-gather_failure { color: #abb2bf; font-style: italic; }
.details-finding.finding-not_applicable { color: #abb2bf; font-style: italic; }

/* Fix hint section — rendered markdown with code block styling */

.details-fix-hint {
    white-space: normal;
}

.details-fix-hint :deep(code) {
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 11px;
    background-color: #1a1a1a;
    color: #e5c07b;
    padding: 1px 6px;
    border-radius: 4px;
}

.details-fix-hint :deep(pre) {
    background: #1a1a1a;
    padding: 8px 12px;
    border-radius: 4px;
    overflow-x: auto;
    margin: 6px 0;
    font-size: 11px;
    line-height: 1.5;
}

.details-fix-hint :deep(pre code) {
    background: transparent;
    padding: 0;
}

/* Commands use monospace but smaller than raw output */
.details-commands {
    font-size: 11px !important;
    padding: 6px 16px !important;
    margin: 0;
    background: transparent;
    color: #8a8a8a;
    white-space: pre-wrap;
    word-break: break-all;
}

/* ConfigMap toggle with green accent to distinguish from blue Details */

.configmap-toggle.active {
    background: #2d6a3f;
    color: white;
    border-color: #2d6a3f;
}

.configmap-toggle:hover {
    background: var(--wire-light-gray);
    color: var(--wire-dark-gray);
    border-color: #ccc;
}

.configmap-toggle.active:hover {
    background: #2d6a3f;
    color: white;
    border-color: #2d6a3f;
}

/* ConfigMap panel with green header tint */
.configmap-panel .details-panel-header {
    background: #141e17;
}

.configmap-panel .details-panel-title {
    color: #98d982;
}

/* Data points used list inside the details panel */

.dp-used-list {
    padding: 4px 16px 8px;
}

/* Section label above each YAML blob when raw_output JSON contains multiple entries */
.yaml-entry-label {
    padding: 5px 16px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #98d982;
    background: #141e17;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
