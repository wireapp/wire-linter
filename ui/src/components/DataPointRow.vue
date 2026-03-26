<!-- DataPointRow.vue - Self-contained DataPoint display with summary row and
     expandable details panel. Used in two places:

     1. DataPointsTree.vue  - renders each leaf in the raw data tab
     2. CheckResultLeafRow.vue - the "Data points used" section in check details

     Shows path, value, description, timestamp, and a Details toggle that
     expands to reveal meta chips, commands, JSON source, and raw output.

     Props:
       data_point - raw DataPoint object from the JSONL
       compact    - when true, renders a narrower layout for embedding inside
                    another details panel (no full-width columns)
-->
<template>
    <!-- Summary row -->
    <div class="dp-row" :class="{ 'dp-row-compact': compact }">
        <span class="dp-row-path">
            <i class="pi pi-database" style="font-size: 11px; opacity: 0.5;"></i>
            {{ data_point.path }}
        </span>
        <!-- Value column: hidden in compact mode (shown in expanded details instead) -->
        <span v-if="!compact" class="dp-row-value">
            <span class="value-cell dp-value">{{ format_value(data_point.value, data_point.unit) }}</span>
        </span>
        <span class="dp-row-desc">{{ data_point.description }}</span>
        <span class="dp-row-meta">
            <span v-if="data_point.metadata?.collected_at" class="dp-row-timestamp">{{ format_timestamp(data_point.metadata.collected_at) }}</span>
            <span v-if="data_point.metadata?.duration_seconds !== undefined" class="dp-row-duration">{{ format_duration(data_point.metadata.duration_seconds, 1) }}s</span>
        </span>
        <span class="dp-row-action">
            <button class="details-toggle" :class="{ active: is_open }" @click="is_open = !is_open">
                <i class="pi pi-code"></i>
                <span>{{ is_open ? 'Hide' : 'Details' }}</span>
            </button>
        </span>
    </div>

    <!-- Expandable details panel -->
    <div v-if="is_open" class="details-panel data-details-panel">
        <div class="details-panel-header">
            <div class="details-panel-title">
                <i class="pi pi-database"></i>
                <span>{{ data_point.path }}</span>
            </div>
            <div class="details-panel-meta">
                <span class="details-panel-desc">{{ data_point.description }}</span>
                <button class="details-close" @click="is_open = false"><i class="pi pi-times"></i></button>
            </div>
            <!-- Value chip - always visible in expanded panel (replaces the hidden column in compact mode) -->
            <div class="dp-meta-chips">
                <span class="dp-chip dp-chip-value">
                    <i class="pi pi-hashtag"></i>{{ format_value(data_point.value, data_point.unit) }}
                </span>
            </div>
            <div v-if="data_point.metadata?.health_info || data_point.metadata?.error || data_point.metadata?.duration_seconds !== undefined || data_point.metadata?.collected_at" class="dp-meta-chips">
                <span v-if="data_point.metadata?.health_info" class="dp-chip dp-chip-info">
                    <i class="pi pi-info-circle"></i>{{ data_point.metadata.health_info }}
                </span>
                <span v-if="data_point.metadata?.error" class="dp-chip dp-chip-error">
                    <i class="pi pi-exclamation-circle"></i>{{ data_point.metadata.error }}
                </span>
                <span v-if="data_point.metadata?.duration_seconds !== undefined" class="dp-chip dp-chip-meta">
                    <i class="pi pi-clock"></i>{{ format_duration(data_point.metadata.duration_seconds, 2) }}s
                </span>
                <span v-if="data_point.metadata?.collected_at" class="dp-chip dp-chip-meta">
                    <i class="pi pi-calendar"></i>{{ format_timestamp(data_point.metadata.collected_at) }}
                </span>
            </div>
            <div v-if="data_point.metadata?.commands?.length" class="dp-commands">
                <div class="dp-commands-label">Commands</div>
                <div v-for="(cmd, idx) in data_point.metadata.commands" :key="idx" class="dp-command">{{ cmd }}</div>
            </div>
        </div>
        <div class="dp-section-label">Source JSON</div>
        <pre class="details-terminal" v-html="highlight_content(json_source)"></pre>
        <template v-if="data_point.raw_output !== undefined">
            <div class="dp-section-label">Raw Output</div>
            <pre v-if="data_point.raw_output" class="details-terminal" v-html="highlight_content(data_point.raw_output)"></pre>
            <div v-else class="details-no-output">Command produced no output.</div>
        </template>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, computed } from 'vue'

// Ours
import type { DataPoint } from '../sample-data'
import { highlight_content } from '../lib/syntax_highlighter'
import { format_value, format_timestamp, format_duration } from '../lib/format_utils'

// -- Props --

const props = defineProps<{
    // The raw DataPoint to render
    data_point: DataPoint
    // Compact layout for embedding inside another details panel
    compact?: boolean
}>()

// -- Local state --

// Self-managed expand/collapse (no parent coordination needed)
const is_open = ref(false)

// JSON view of metadata (excluding raw_output which is shown separately)
const json_source = computed((): string => {
    const { raw_output, ...rest } = props.data_point
    return JSON.stringify(rest, null, 2)
})
</script>

<style scoped>
/* Summary row layout */

.dp-row {
    display: flex;
    align-items: center;
    padding: 6px 12px;
    border-bottom: 1px solid var(--wire-border);
    font-size: 13px;
    gap: 8px;
}

.dp-row:hover {
    background: rgba(255, 255, 255, 0.04);
    border-left: 2px solid #4dcfcf;
    padding-left: 10px;
}

.dp-row-path {
    flex: 0 0 30%;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: #c8c8c8;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.dp-row-value {
    flex: 0 0 12%;
    min-width: 0;
}

.dp-row-desc {
    flex: 1;
    min-width: 0;
    font-size: 12px;
    color: #888;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.dp-row-meta {
    flex: 0 0 110px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    align-items: flex-end;
}

.dp-row-timestamp {
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    color: #999;
    white-space: nowrap;
}

.dp-row-duration {
    font-size: 10px;
    color: #aaa;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.dp-row-action {
    flex: 0 0 70px;
    display: flex;
    justify-content: flex-end;
    align-items: center;
}

/* Compact mode for embedding inside check details panels */

.dp-row-compact {
    padding: 5px 0;
    border-bottom-color: rgba(255, 255, 255, 0.06);
    border-left: 2px solid transparent;
    font-size: 12px;
    background: transparent;
}

.dp-row-compact:hover {
    background: rgba(255, 255, 255, 0.03);
    border-left: 2px solid #4dcfcf;
    padding-left: 0;
}

.dp-row-compact .dp-row-path {
    font-size: 11px;
    color: #c8c8c8;
}

.dp-row-compact .dp-row-value {
    color: #a8a8a8;
}

.dp-row-compact .dp-row-desc {
    color: #888;
}

.dp-row-compact .dp-row-timestamp {
    color: #777;
}

.dp-row-compact .dp-row-duration {
    color: #666;
}

/* Data details panel header - teal accent like the raw data tab */

.data-details-panel .details-panel-header {
    background: #0e1c1e;
}

.data-details-panel .details-panel-title {
    color: #4dcfcf;
}

/* Metadata chips */

.dp-meta-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
}

.dp-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 12px;
    font-size: 11px;
    line-height: 1;
}

.dp-chip-value {
    background: rgba(255, 255, 255, 0.08);
    color: #e8e8e8;
    border: 1px solid rgba(255, 255, 255, 0.15);
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
}

.dp-chip-info {
    background: rgba(77, 207, 207, 0.12);
    color: #4dcfcf;
    border: 1px solid rgba(77, 207, 207, 0.25);
}

.dp-chip-error {
    background: rgba(207, 34, 46, 0.15);
    color: #ff7070;
    border: 1px solid rgba(207, 34, 46, 0.3);
}

.dp-chip-meta {
    background: rgba(255, 255, 255, 0.07);
    color: #888;
    border: 1px solid rgba(255, 255, 255, 0.10);
}

/* Commands */

.dp-commands {
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.dp-commands-label {
    font-size: 10px;
    font-weight: 600;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 5px;
}

.dp-command {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #c8c8c8;
    background: rgba(0, 0, 0, 0.35);
    padding: 4px 10px;
    border-radius: 4px;
    margin-bottom: 3px;
    overflow-x: auto;
    white-space: nowrap;
    border-left: 2px solid #4dcfcf;
}

/* Section labels */

.dp-section-label {
    padding: 5px 16px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: #4dcfcf;
    background: #0e1c1e;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
}

/* Value cell styling */

.dp-value {
    color: #c8c8c8;
}

.dp-row-compact .dp-value {
    color: #a8a8a8;
}
</style>
