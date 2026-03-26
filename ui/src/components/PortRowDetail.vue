<template>
    <div class="details-panel port-details-panel">
        <div class="details-panel-header">
            <div class="details-panel-title">
                <i class="pi pi-shield"></i>
                <span>Firewall Analysis: {{ port_row.target_name }}:{{ port_row.port }}</span>
            </div>
            <button class="details-close" @click="emit('close')">
                <i class="pi pi-times"></i>
            </button>
        </div>
        <div class="port-analysis-content">
            <template v-if="analysis">
                <div class="analysis-section">
                    <div class="analysis-label">Blocking Rule</div>
                    <pre class="analysis-rule">{{ analysis.rule_text }}</pre>
                </div>
                <div class="analysis-section">
                    <div class="analysis-label">Explanation</div>
                    <p class="analysis-text">{{ analysis.explanation }}</p>
                </div>
                <div class="analysis-section">
                    <div class="analysis-label">Fix Command</div>
                    <div class="analysis-fix-row">
                        <pre class="analysis-fix-cmd">{{ analysis.fix_command }}</pre>
                        <PortCopyButton :command="analysis.fix_command" />
                    </div>
                </div>
            </template>
            <template v-else-if="has_firewall_data">
                <div class="analysis-section">
                    <p class="analysis-text analysis-no-data">
                        Firewall data was collected but no blocking rule was found on either host.
                        The port may be blocked by network routing, security groups, or the service may not be listening.
                    </p>
                </div>
            </template>
            <template v-else>
                <div class="analysis-section">
                    <p class="analysis-text analysis-no-data">
                        No firewall data collected for {{ port_row.target_name }}.
                        Run the gatherer with <code>firewall_rules</code> target to enable firewall analysis.
                    </p>
                </div>
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { computed } from 'vue'

// Ours
import type { PortLink, FirewallData } from '../lib/port_types'
import type { BlockingRuleAnalysis } from '../lib/firewall_types'
import { find_blocking_rule } from '../lib/firewall_analyzer'
import PortCopyButton from './PortCopyButton.vue'

// -- Props --

const props = defineProps<{
    port_row: PortLink
    firewall_data_map: Map<string, FirewallData>
}>()

const emit = defineEmits<{
    close: []
}>()

// -- Analysis --

// compute firewall analysis once per render so we don't parse rules multiple
// times per template render (which would happen if we called find_blocking_rule
// inline in the template)
const analysis = computed<BlockingRuleAnalysis | null>(() => {
    // check target host's firewall for incoming blocks
    const target_fw = props.firewall_data_map.get(props.port_row.target_name)
    if (target_fw) {
        const result = find_blocking_rule(target_fw, props.port_row.source_ip, props.port_row.port, props.port_row.protocol, 'incoming')
        if (result) return result
    }

    // check source host's firewall for outgoing blocks
    const source_fw = props.firewall_data_map.get(props.port_row.source_name)
    if (source_fw) {
        const result = find_blocking_rule(source_fw, props.port_row.target_ip, props.port_row.port, props.port_row.protocol, 'outgoing')
        if (result) return result
    }

    return null
})

// whether firewall data exists for either host
const has_firewall_data = computed<boolean>(() => {
    return props.firewall_data_map.has(props.port_row.target_name) || props.firewall_data_map.has(props.port_row.source_name)
})
</script>

<style scoped>
/* indent to align with port leaf rows */
.port-details-panel {
    margin: 0 16px 8px 64px;
}

.port-analysis-content {
    padding: 12px 16px;
}

.analysis-section {
    margin-bottom: 12px;
}

.analysis-section:last-child {
    margin-bottom: 0;
}

.analysis-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--wire-medium-gray);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}

.analysis-rule {
    background: #1a1a2e;
    color: #e0e0e0;
    padding: 8px 12px;
    border-radius: 6px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
}

.analysis-text {
    font-size: 13px;
    color: var(--wire-dark-gray);
    line-height: 1.5;
}

.analysis-no-data {
    color: var(--wire-medium-gray);
    font-style: italic;
}

.analysis-fix-row {
    display: flex;
    align-items: stretch;
    gap: 0;
}

.analysis-fix-cmd {
    flex: 1;
    background: #1a1a2e;
    color: #4ade80;
    padding: 8px 12px;
    border-radius: 6px 0 0 6px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
}
</style>
