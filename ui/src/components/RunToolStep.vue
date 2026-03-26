<!-- RunToolStep.vue - Step 4: Run Tool

    Shows the commands the operator needs to run, dynamically generated
    based on the Step 2 configuration. Adapts for DMZ calling, client
    probes, and SSH alternatives.

    Props:
      setup - the SetupData object from Step 2
    Emits: back, next
-->
<template>
    <div class="step-content">
        <h1 class="step-title">Run the Tool</h1>
        <p class="step-description">
            Run the following commands to collect data from your Wire deployment.
            Copy the settings file to your admin host first, then run the commands below.
        </p>

        <!-- Primary: backend on admin host -->
        <h3 class="command-label">1. Backend data (run on admin host)</h3>
        <p class="command-description">
            Run this directly on the Wire admin host to collect backend infrastructure data.
        </p>
        <div class="terminal-block">
            <button class="copy-btn" :class="{ copied: copied_backend }" @click="copy_backend(backend_command.copy)">
                {{ copied_backend ? 'Copied!' : 'Copy' }}
            </button>
            <pre><span class="prompt">$ </span><span class="command" v-html="style_continuations(backend_command.display)"></span></pre>
        </div>

        <!-- DMZ calling: second backend command -->
        <template v-if="setup.calling_in_dmz">
            <h3 class="command-label" style="margin-top: 20px;">2. Calling DMZ cluster (run on admin host)</h3>
            <p class="command-description">
                Since calling is in a separate DMZ cluster, run the tool again with a different
                kubeconfig pointing at the calling cluster.
            </p>
            <div class="terminal-block">
                <button class="copy-btn" :class="{ copied: copied_dmz }" @click="copy_dmz(dmz_command.copy)">
                    {{ copied_dmz ? 'Copied!' : 'Copy' }}
                </button>
                <pre><span class="prompt">$ </span><span class="command" v-html="style_continuations(dmz_command.display)"></span></pre>
            </div>
        </template>

        <!-- Client probes -->
        <h3 class="command-label" style="margin-top: 20px;">
            {{ setup.calling_in_dmz ? '3' : '2' }}. Client reachability (run from each user network)
        </h3>
        <p class="command-description">
            Run this from each network where Wire clients will operate (office LAN, VPN, internet, etc.)
            to verify they can reach the backend. Replace <code>&lt;network-name&gt;</code> with a label
            for the network.
        </p>
        <div class="terminal-block">
            <button class="copy-btn" :class="{ copied: copied_client }" @click="copy_client(client_command.copy)">
                {{ copied_client ? 'Copied!' : 'Copy' }}
            </button>
            <pre><span class="prompt">$ </span><span class="command" v-html="style_continuations(client_command.display)"></span></pre>
        </div>

        <!-- Network name input with presets -->
        <div class="network-name-box">
            <label class="network-name-label" for="client-network-name">Network name:</label>
            <input
                id="client-network-name"
                v-model="client_network_name"
                type="text"
                class="network-name-input"
                placeholder="e.g. office-lan"
            />
            <div class="network-presets">
                <button
                    v-for="preset in network_presets"
                    :key="preset.value"
                    class="preset-btn"
                    :class="{ active: client_network_name === preset.value }"
                    @click="client_network_name = preset.value"
                >
                    {{ preset.label }}
                </button>
            </div>
        </div>

        <!-- SSH alternative (collapsible) -->
        <details class="ssh-alternative" style="margin-top: 20px;">
            <summary class="ssh-summary">Alternative: run from a remote machine via SSH</summary>
            <p class="command-description" style="margin-top: 8px;">
                If you cannot run scripts directly on the admin host, use this command from any machine
                that can SSH into the admin host.
            </p>
            <div class="terminal-block">
                <button class="copy-btn" :class="{ copied: copied_ssh }" @click="copy_ssh(ssh_command.copy)">
                    {{ copied_ssh ? 'Copied!' : 'Copy' }}
                </button>
                <pre><span class="prompt">$ </span><span class="command" v-html="style_continuations(ssh_command.display)"></span></pre>
            </div>
        </details>

        <div class="step-actions">
            <Button label="Back" severity="secondary" icon="pi pi-arrow-left" @click="$emit('back')" />
            <Button label="Next" icon="pi pi-arrow-right" icon-pos="right" @click="$emit('next')" />
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, computed } from 'vue'
import Button from 'primevue/button'

// Ours
import type { SetupData } from '../lib/settings_yaml'
import { use_clipboard } from '../lib/clipboard'

const { setup } = defineProps<{
    setup: SetupData
}>()

defineEmits<{
    (e: 'back'): void
    (e: 'next'): void
}>()

// Separate clipboard handles per button
const { copy: copy_backend, is_copied: copied_backend } = use_clipboard()
const { copy: copy_dmz,     is_copied: copied_dmz }     = use_clipboard()
const { copy: copy_client,  is_copied: copied_client }   = use_clipboard()
const { copy: copy_ssh,     is_copied: copied_ssh }      = use_clipboard()

// Replace backslash continuations with a styled span so they appear
// dimmer than the actual command text in the terminal block
function style_continuations(display: string): string {
    // Escape HTML entities first so we don't inject anything dangerous,
    // then wrap the \ characters in a span with a dim class
    return display
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\\/g, '<span class="continuation">\\</span>')
}

// Base runner command parts
const config_file = '/tmp/wire-facts-settings.yaml'
const runner_script = 'python3 src/script/runner.py'
// The default kubeconfig path for Wire-managed kubespray clusters.
// On Wire admin hosts, ~/.kube/config is typically empty — the real kubeconfig
// lives at ~/wire-server-deploy/ansible/inventory/kubeconfig.dec.
// If the user hasn't changed it from this default, we omit --kubeconfig from the
// command (the runner's Docker wrapper finds it automatically by mounting
// wire-server-deploy into the container).
const default_kubeconfig = '~/wire-server-deploy/ansible/inventory/kubeconfig.dec'

// Builds both a display version (multi-line with \ continuations)
// and a copy version (single line, no \ or newlines)
function build_command(parts: string[]): { display: string; copy: string } {
    return {
        copy:    parts.join(' '),
        display: parts.join(' \\\n    '),
    }
}

// Whether the user changed the main kubeconfig from the default
const has_custom_kubeconfig = computed((): boolean => {
    const path: string = setup.kubeconfig_path.trim()
    return path !== '' && path !== default_kubeconfig
})

// Primary backend command (run on admin host)
const backend_parts = computed((): string[] => {
    const parts: string[] = [
        runner_script,
        '--source admin-host',
    ]
    // Only include --kubeconfig if the user changed it from the default
    if (has_custom_kubeconfig.value) {
        parts.push(`--kubeconfig "${setup.kubeconfig_path.trim()}"`)
    }
    if (setup.calling_in_dmz) {
        parts.push('--cluster-type main')
    }
    parts.push('--network-name "main-cluster"')
    parts.push(`--config ${config_file}`)
    parts.push('--output /tmp/wire-facts-results.jsonl')
    return parts
})
const backend_command = computed(() => build_command(backend_parts.value))

// DMZ calling cluster command (only shown when calling_in_dmz)
const dmz_kubeconfig = computed((): string => {
    const path: string = setup.calling_kubeconfig_path.trim()
    return path || '/path/to/calling-kubeconfig'
})
const dmz_command = computed(() => build_command([
    runner_script,
    '--source admin-host',
    '--cluster-type calling',
    `--kubeconfig "${dmz_kubeconfig.value}"`,
    '--network-name "calling-dmz"',
    `--config ${config_file}`,
    '--output /tmp/wire-facts-calling.jsonl',
]))

// Client network name — filled by the user or preset buttons
const client_network_name = ref('')

// Slugified version for filenames (lowercase, hyphens instead of spaces)
const client_name_slug = computed((): string => {
    const name: string = client_network_name.value.trim()
    if (!name) return '<name>'
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
})

// Display name for --network-name (quoted, or placeholder)
const client_name_display = computed((): string => {
    const name: string = client_network_name.value.trim()
    return name ? `"${name}"` : '"<network-name>"'
})

// Client probe command — uses the entered name or placeholders
const client_command = computed(() => build_command([
    runner_script,
    '--source client',
    `--network-name ${client_name_display.value}`,
    `--config ${config_file}`,
    `--output /tmp/wire-facts-client-${client_name_slug.value}.jsonl`,
]))

// Preset network names
const network_presets: { label: string; value: string }[] = [
    { label: 'Internet',       value: 'internet' },
    { label: 'Intranet',       value: 'intranet' },
    { label: 'VPN',            value: 'vpn' },
    { label: 'Office LAN',     value: 'office-lan' },
    { label: 'Home',           value: 'home' },
    { label: 'Guest WiFi',     value: 'guest-wifi' },
]

// SSH alternative command (run from remote machine) — respects custom kubeconfig
const ssh_command = computed(() => {
    const parts: string[] = [
        runner_script,
        '--source ssh-into-admin-host',
    ]
    if (has_custom_kubeconfig.value) {
        parts.push(`--kubeconfig "${setup.kubeconfig_path.trim()}"`)
    }
    parts.push('--network-name "main-cluster"')
    parts.push(`--config ${config_file}`)
    parts.push('--output /tmp/wire-facts-results.jsonl')
    return build_command(parts)
})
</script>

<style scoped>
.step-content {
    animation: fade-in 0.3s ease;
}

@keyframes fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

.step-title {
    font-size: 28px;
    font-weight: 700;
    color: var(--wire-black);
    margin-bottom: 8px;
}

.step-description {
    font-size: 15px;
    color: var(--wire-medium-gray);
    margin-bottom: 24px;
    line-height: 1.6;
}

.step-description code {
    background: var(--wire-light-gray);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
}

.command-label {
    font-size: 15px;
    font-weight: 600;
    color: var(--wire-dark-gray);
    margin-bottom: 6px;
}

.command-description {
    font-size: 13px;
    color: var(--wire-medium-gray);
    margin-bottom: 10px;
    line-height: 1.5;
}

.terminal-block {
    position: relative;
    background: #1e1e2e;
    border-radius: 8px;
    padding: 16px 20px;
    overflow-x: auto;
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    line-height: 1.6;
}

.terminal-block pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
}

.prompt {
    color: #89b4fa;
    user-select: none;
}

.command {
    color: #cdd6f4;
}

/* Line continuation backslashes — dimmed so they don't distract from the
   actual command arguments */
.command :deep(.continuation) {
    color: #585b70;
}

.copy-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 500;
    border: 1px solid #45475a;
    border-radius: 4px;
    background: #313244;
    color: #cdd6f4;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
}

.copy-btn:hover {
    background: #45475a;
}

.copy-btn.copied {
    background: #a6e3a1;
    color: #1e1e2e;
    border-color: #a6e3a1;
}

/* SSH alternative collapsible section */
.ssh-alternative {
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    padding: 12px 16px;
}

.ssh-summary {
    font-size: 14px;
    font-weight: 500;
    color: var(--wire-medium-gray);
    cursor: pointer;
}

.ssh-summary:hover {
    color: var(--wire-dark-gray);
}

/* Network name input box with preset buttons */
.network-name-box {
    margin-top: 12px;
    padding: 12px 16px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    background: var(--wire-white);
}

.network-name-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--wire-dark-gray);
    margin-right: 8px;
}

.network-name-input {
    padding: 6px 10px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 6px;
    font-size: 13px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    color: var(--wire-dark-gray);
    width: 200px;
    transition: border-color 0.15s;
}

.network-name-input:focus {
    outline: none;
    border-color: var(--wire-blue);
}

.network-presets {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
}

.preset-btn {
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
    border: 1px solid var(--wire-border-gray);
    border-radius: 14px;
    background: var(--wire-white);
    color: var(--wire-medium-gray);
    cursor: pointer;
    transition: all 0.15s;
}

.preset-btn:hover {
    border-color: var(--wire-blue);
    color: var(--wire-blue);
}

.preset-btn.active {
    background: var(--wire-blue);
    border-color: var(--wire-blue);
    color: white;
}

.step-actions {
    display: flex;
    justify-content: space-between;
    margin-top: 32px;
}
</style>
