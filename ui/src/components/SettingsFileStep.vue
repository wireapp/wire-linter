<!--
    SettingsFileStep.vue - Step 3 of the Wire Fact Gathering wizard.

    Shows generated settings YAML from Step 2. Two tabs:
      - File:    Raw YAML to save as wire-facts-settings.yaml
      - Command: echo command to write it to /tmp/

    Props: setup (SetupData object)
    Emits: back, next
-->
<template>
    <div class="step-content">
        <h1 class="step-title">Settings File</h1>
        <p class="step-description">
            <br/>
            Save this as <code>/tmp/wire-facts-settings.yaml</code> on your admin host, in the same directory where you'll run the fact gathering tool.
            <br/>
            <br/>
        </p>

        <div class="tab-bar">
            <button
                class="tab-btn"
                :class="{ active: active_tab === 'file' }"
                @click="active_tab = 'file'"
            >File</button>
            <button
                class="tab-btn"
                :class="{ active: active_tab === 'command' }"
                @click="active_tab = 'command'"
            >Command</button>
        </div>

        <div class="terminal-block">
            <button
                v-if="active_tab === 'file'"
                class="copy-btn"
                :class="{ copied: copied_yaml }"
                @click="copy_yaml(generated_yaml)"
            >{{ copied_yaml ? 'Copied!' : 'Copy' }}</button>
            <button
                v-else
                class="copy-btn"
                :class="{ copied: copied_cmd }"
                @click="copy_cmd(command_text)"
            >{{ copied_cmd ? 'Copied!' : 'Copy' }}</button>

            <pre v-if="active_tab === 'file'">{{ generated_yaml }}</pre>
            <pre v-else>{{ command_text }}</pre>
        </div>

        <div class="step-actions">
            <Button label="Back" severity="secondary" icon="pi pi-arrow-left" @click="emit('back')" />
            <Button label="Next" icon="pi pi-arrow-right" icon-pos="right" @click="emit('next')" />
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { computed, ref } from 'vue'
import Button from 'primevue/button'
// Ours
import type { SetupData } from '../lib/settings_yaml'
import { generate_settings_yaml } from '../lib/settings_yaml'
import { use_clipboard } from '../lib/clipboard'

const props = defineProps<{
    setup: SetupData
}>()

const emit = defineEmits<{
    back: []
    next: []
}>()

const active_tab = ref<'file' | 'command'>('file')

// separate clipboard handles for each tab
const { copy: copy_yaml, is_copied: copied_yaml } = use_clipboard()
const { copy: copy_cmd, is_copied: copied_cmd } = use_clipboard()

// generate YAML from form data
const generated_yaml = computed(() => generate_settings_yaml(props.setup))

// heredoc command that writes the file. single-quoted delimiter ('EOF')
// prevents all shell interpretation — no escaping needed for !, $, `, etc.
const command_text = computed(
    () => `cat <<'EOF' > /tmp/wire-facts-settings.yaml\n${generated_yaml.value}\nEOF`
)
</script>

<style scoped>
.tab-bar {
    display: flex;
    gap: 0;
    margin-bottom: -1px;  /* overlap terminal-block border for connected look */
    position: relative;
    z-index: 1;
}

.tab-btn {
    padding: 7px 20px;
    font-size: 13px;
    font-family: inherit;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    background: #111128;
    color: #888;
    transition: background 0.15s, color 0.15s;
}

.tab-btn:hover {
    background: #1a1a35;
    color: #ccc;
}

.tab-btn.active {
    background: #1a1a2e;
    color: #e0e0e0;
    border-color: rgba(255, 255, 255, 0.18);
}

/* no top corners so it connects flush with tabs */
.terminal-block {
    border-radius: 0 0 8px 8px;
}
</style>
