<!--
    HostFileStep.vue - Step 1 of the Wire Fact Gathering wizard.

    Two textareas side by side for INI and YAML Ansible inventory formats, plus a
    "Parse & Pre-fill" button and a results summary. All parsing state stays here.

    When parsing works, we emit 'parsed' with the ParsedHosts payload. Parent applies
    it to the setup form. Next/Skip are emitted as 'next' events.

    parse_status is a single object { type, message } so we can't accidentally show
    both success and error at the same time.
-->
<template>
    <div class="step-content">
        <h1 class="step-title">Pre-fill config from files</h1>
        <p class="step-description">
            Provide your <code>hosts.ini</code> file (INI format), your inventory file e.g. <code>wiab-staging.yml</code> (YAML format), or both.
            This step is optional - you can skip it and enter the details manually.
        </p>

        <div class="hostfile-section">
            <!-- Two side-by-side textareas for INI and YAML -->
            <div class="hostfile-dual-inputs">
                <div class="hostfile-input-col">
                    <div class="hostfile-input-header">
                        <span class="hostfile-input-label">
                            <i class="pi pi-file"></i>
                            hosts.ini
                        </span>
                        <Button
                            label="Use Sample"
                            severity="secondary"
                            size="small"
                            outlined
                            @click="load_sample_ini"
                        />
                    </div>
                    <Textarea
                        v-model="hostfile_ini"
                        placeholder="Paste the contents of your hosts.ini file here..."
                        :rows="16"
                        fluid
                        style="font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px;"
                    />
                </div>

                <div class="hostfile-input-col">
                    <div class="hostfile-input-header">
                        <span class="hostfile-input-label">
                            <i class="pi pi-file"></i>
                            inventory.yml
                        </span>
                        <Button
                            label="Use Sample"
                            severity="secondary"
                            size="small"
                            outlined
                            @click="load_sample_yaml"
                        />
                    </div>
                    <Textarea
                        v-model="hostfile_yaml"
                        placeholder="Paste the contents of your inventory file here (e.g. wiab-staging.yml)..."
                        :rows="16"
                        fluid
                        style="font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 12px;"
                    />
                </div>
            </div>

            <!-- Parse button -->
            <div class="hostfile-actions-row">
                <Button
                    label="Parse & Pre-fill"
                    icon="pi pi-cog"
                    @click="parse_and_prefill"
                    :disabled="!hostfile_ini.trim() && !hostfile_yaml.trim()"
                />
            </div>

            <!-- Single status panel: only one of error or success can be shown at a time -->
            <div v-if="parse_status.type" class="hostfile-results">
                <!-- Error state: YAML threw a YAMLException -->
                <Message v-if="parse_status.type === 'error'" severity="error" :closable="false">
                    <template #default>
                        <div class="parse-result-content">
                            <strong>YAML parse error:</strong> {{ parse_status.message }}
                        </div>
                    </template>
                </Message>

                <!-- Success state: parse completed, show summary of extracted hosts -->
                <template v-else>
                    <Message severity="success" :closable="false">
                        <template #default>
                            <div class="parse-result-content">
                                <strong>Host file parsed successfully.</strong>
                                Pre-filled {{ prefilled_field_count }} configuration fields.
                            </div>
                        </template>
                    </Message>

                    <div class="parsed-summary">
                        <div v-if="parsed_hosts.kube_nodes.length" class="parsed-group parsed-group-full">
                            <span class="parsed-label">Kube Nodes <span class="parsed-count">{{ parsed_hosts.kube_nodes.length }}</span></span>
                            <div class="parsed-node-list">
                                <span v-for="ip in parsed_hosts.kube_nodes" :key="ip" class="parsed-node-ip">{{ ip }}</span>
                            </div>
                        </div>
                        <div v-if="parsed_hosts.data_nodes.length" class="parsed-group parsed-group-full">
                            <span class="parsed-label">Data Nodes <span class="parsed-count">{{ parsed_hosts.data_nodes.length }}</span></span>
                            <div class="parsed-node-list">
                                <span v-for="ip in parsed_hosts.data_nodes" :key="ip" class="parsed-node-ip">{{ ip }}</span>
                            </div>
                        </div>
                        <div v-if="parsed_hosts.cassandra.length" class="parsed-group">
                            <span class="parsed-label">Cassandra</span>
                            <span class="parsed-value">{{ parsed_hosts.cassandra.join(', ') }}</span>
                        </div>
                        <div v-if="parsed_hosts.elasticsearch.length" class="parsed-group">
                            <span class="parsed-label">Elasticsearch</span>
                            <span class="parsed-value">{{ parsed_hosts.elasticsearch.join(', ') }}</span>
                        </div>
                        <div v-if="parsed_hosts.minio.length" class="parsed-group">
                            <span class="parsed-label">MinIO</span>
                            <span class="parsed-value">{{ parsed_hosts.minio.join(', ') }}</span>
                        </div>
                        <div v-if="parsed_hosts.kubenode.length" class="parsed-group">
                            <span class="parsed-label">Kubernetes</span>
                            <span class="parsed-value">{{ parsed_hosts.kubenode.join(', ') }}</span>
                        </div>
                        <div v-if="parsed_hosts.domain" class="parsed-group">
                            <span class="parsed-label">Domain</span>
                            <span class="parsed-value">{{ parsed_hosts.domain }}</span>
                        </div>
                        <div v-if="parsed_hosts.ansible_user" class="parsed-group">
                            <span class="parsed-label">SSH User</span>
                            <span class="parsed-value">{{ parsed_hosts.ansible_user }}</span>
                        </div>
                        <div v-if="parsed_hosts.ssh_key_path" class="parsed-group">
                            <span class="parsed-label">SSH Key</span>
                            <span class="parsed-value">{{ parsed_hosts.ssh_key_path }}</span>
                        </div>
                    </div>
                </template>
            </div>
        </div>

        <div class="step-actions">
            <span></span>
            <div class="step-actions-right">
                <Button label="Skip" severity="secondary" icon="pi pi-forward" @click="emit('next')" />
                <Button
                    label="Next"
                    icon="pi pi-arrow-right"
                    icon-pos="right"
                    @click="emit('next')"
                    :disabled="parse_status.type !== 'success'"
                />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { ref, computed } from 'vue'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import Message from 'primevue/message'
// Ours
import type { ParsedHosts, HostfileSetupFields } from '../lib/hostfile_types'
import {
    parse_hosts_ini,
    parse_hosts_yaml,
    merge_parsed_hosts,
    apply_parsed_hosts_to_setup,
} from '../lib/hostfile_parser'
import {
    SAMPLE_HOSTFILE_INI,
    SAMPLE_HOSTFILE_YAML,
} from '../lib/hostfile_samples'

const emit = defineEmits<{
    // Emitted when the host file is parsed with the merged ParsedHosts result
    parsed: [hosts: ParsedHosts]
    // Emitted when the user clicks Next or Skip
    next: []
}>()

// -- State --

// separate textareas for INI and YAML inventory formats
const hostfile_ini  = ref('')
const hostfile_yaml = ref('')

// single status object: type is null, 'success', or 'error'. using one object
// instead of separate flags makes it impossible to show both success and error
const parse_status = ref<{ type: 'success' | 'error' | null; message: string }>({
    type:    null,
    message: '',
})

// the merged parse result after parse_and_prefill succeeds
const parsed_hosts = ref<ParsedHosts>({
    cassandra:      [],
    elasticsearch:  [],
    minio:          [],
    kubenode:       [],
    kube_nodes:     [],
    data_nodes:     [],
    admin_host:     '',
    domain:         '',
    ansible_user:   '',
    ssh_key_path:   '',
    db_ssh_key:     '',
})

// -- Computed --

// how many fields got pre-filled apply to a blank setup object and count non-empty
// results so the number stays in sync with apply_parsed_hosts_to_setup automatically
const prefilled_field_count = computed(() => {
    const blank_setup: HostfileSetupFields = {
        cassandra_host:     '',
        elasticsearch_host: '',
        minio_host:         '',
        admin_host_ip:      '',
        cluster_domain:     '',
        admin_user:         '',
        ssh_key_path:       '',
        db_ssh_user:        '',
        db_ssh_key:         '',
        kube_nodes:         [],
        data_nodes:         [],
    }
    apply_parsed_hosts_to_setup(parsed_hosts.value, blank_setup)
    let count = 0
    for (const value of Object.values(blank_setup)) {
        if (Array.isArray(value) ? value.length > 0 : value !== '') count++
    }
    return count
})

// -- Functions --

// parse whichever textareas have content, merge, and emit
function parse_and_prefill() {
    const ini_content  = hostfile_ini.value.trim()
    const yaml_content = hostfile_yaml.value.trim()

    // reset status so we don't show old results alongside new ones
    parse_status.value = { type: null, message: '' }

    // parse both if available; YAML can throw if malformed
    const ini_result = ini_content ? parse_hosts_ini(ini_content) : null
    let yaml_result: ReturnType<typeof parse_hosts_yaml> | null = null
    if (yaml_content) {
        try {
            yaml_result = parse_hosts_yaml(yaml_content)
        } catch (error: unknown) {
            const message = error instanceof Error ? error.message : String(error)
            parse_status.value = { type: 'error', message }
            return
        }
    }

    // merge or use whichever is available
    let hosts: ParsedHosts
    if (ini_result && yaml_result) {
        hosts = merge_parsed_hosts(ini_result, yaml_result)
    } else if (ini_result) {
        hosts = ini_result
    } else if (yaml_result) {
        hosts = yaml_result
    } else {
        return
    }

    parsed_hosts.value = hosts
    parse_status.value = { type: 'success', message: '' }
    emit('parsed', hosts)
}

// load the sample INI inventory
function load_sample_ini() {
    hostfile_ini.value = SAMPLE_HOSTFILE_INI
}

// load the sample YAML inventory
function load_sample_yaml() {
    hostfile_yaml.value = SAMPLE_HOSTFILE_YAML
}
</script>

<style scoped>
/* Host file step layout */
.hostfile-section {
    margin-top: 8px;
}

.hostfile-dual-inputs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
}

.hostfile-input-col {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.hostfile-input-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.hostfile-input-label {
    font-size: 14px;
    font-weight: 600;
    color: var(--wire-dark-gray);
    display: flex;
    align-items: center;
    gap: 6px;
}

.hostfile-actions-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 16px;
}

/* Parse results summary */
.hostfile-results {
    margin-top: 16px;
}

.parse-result-content {
    font-size: 14px;
}

.parsed-summary {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 16px;
    padding: 16px;
    background: var(--wire-light-gray);
    border-radius: 8px;
}

.parsed-group {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.parsed-group-full {
    grid-column: 1 / -1;
}

.parsed-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--wire-medium-gray);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.parsed-value {
    font-size: 13px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    color: var(--wire-dark-gray);
}

.parsed-node-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
}

.parsed-node-ip {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--wire-blue);
    color: white;
    font-size: 12px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
}

.parsed-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    background: var(--wire-blue);
    color: white;
    font-size: 10px;
    font-weight: 700;
    margin-left: 4px;
}

</style>
