<!--
    ConfigurationStep.vue

    Step 2 of the Wire Fact Gathering Tool wizard - the connection details form.
    Extracted from App.vue to keep the parent lean. Owns all node-management
    helpers (add/remove/update for kube and data nodes) and the CSS for the
    form grid, nodes panels, and node rows.

    Props / model:
      v-model:setup      - the SetupData object (two-way bound)
      hostfile_parsed    - whether a host file was already imported (shows pre-fill note)

    Emits:
      back   - user clicked Back
      next   - user clicked Next
-->
<template>
    <div class="step-content">
        <h1 class="step-title">Configuration</h1>
        <p class="step-description">
            Provide connection details for your Wire backend installation.
            <span v-if="hostfile_parsed" class="prefill-note">
                Fields have been pre-filled from your host file. Review and adjust as needed.
            </span>
        </p>

        <div class="setup-form">
            <h2 class="section-title">Connection Details</h2>

            <div class="form-grid">
                <IpInput
                    v-model="setup.admin_host_ip"
                    label="Admin Host IP *"
                    placeholder="10.0.0.1"
                    input-id="admin_host_ip"
                    :invalid="validation_errors.has('admin_host_ip')"
                />
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="admin_user" v-model="setup.admin_user" placeholder="wire-admin" fluid />
                        <label for="admin_user">Admin Username</label>
                    </FloatLabel>
                </div>
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="cluster_domain" v-model="setup.cluster_domain" placeholder="wire.example.com" fluid
                            :invalid="validation_errors.has('cluster_domain')" />
                        <label for="cluster_domain">Cluster Domain *</label>
                    </FloatLabel>
                </div>
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="k8s_namespace" v-model="setup.k8s_namespace" placeholder="wire" fluid
                            :invalid="validation_errors.has('k8s_namespace')" />
                        <label for="k8s_namespace">Kubernetes Namespace *</label>
                    </FloatLabel>
                </div>
                <IpInput
                    v-model="setup.cassandra_host"
                    label="Cassandra Host"
                    placeholder="10.0.0.10"
                    input-id="cassandra_host"
                />
                <IpInput
                    v-model="setup.elasticsearch_host"
                    label="Elasticsearch Host"
                    placeholder="10.0.0.11"
                    input-id="elasticsearch_host"
                />
                <IpInput
                    v-model="setup.minio_host"
                    label="MinIO Host"
                    placeholder="10.0.0.12"
                    input-id="minio_host"
                />
                <IpInput
                    v-model="setup.postgres_host"
                    label="PostgreSQL Host"
                    placeholder="10.0.0.13"
                    input-id="postgres_host"
                />
                <IpInput
                    v-model="setup.rabbitmq_host"
                    label="RabbitMQ Host"
                    placeholder="10.0.0.14"
                    input-id="rabbitmq_host"
                />
            </div>

            <h2 class="section-title" style="margin-top: 32px;">SSH - This Machine to Admin Host</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                SSH key on <em>this machine</em> (where you run the script) to reach the admin host. This is not required if you run the information gathering script directly on the admin host.
            </p>

            <div class="form-grid">
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="ssh_key_path" v-model="setup.ssh_key_path" placeholder="~/.ssh/id_ed25519" fluid />
                        <label for="ssh_key_path">SSH Key (local)</label>
                    </FloatLabel>
                </div>
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="ssh_port" v-model="setup.ssh_port" placeholder="22" fluid
                            @input="setup.ssh_port = setup.ssh_port.replace(/[^0-9]/g, '')" />
                        <label for="ssh_port">SSH Port</label>
                    </FloatLabel>
                </div>
            </div>

            <h2 class="section-title" style="margin-top: 32px;">SSH - Admin Host to Cluster Nodes</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                SSH key on <em>the admin host</em> to reach kubenodes and database VMs.
                The runner SSHes to the admin host first (unless running directly on it), then jumps from there to
                each cluster node. Leave empty if the same key works for both hops.
            </p>

            <div class="form-grid">
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="db_ssh_user" v-model="setup.db_ssh_user" placeholder="demo" fluid />
                        <label for="db_ssh_user">SSH User (on admin host)</label>
                    </FloatLabel>
                </div>
                <div class="form-field">
                    <FloatLabel>
                        <InputText id="db_ssh_key" v-model="setup.db_ssh_key" placeholder="/home/demo/wire-server-deploy/ssh/id_ed25519" fluid />
                        <label for="db_ssh_key">SSH Key (on admin host)</label>
                    </FloatLabel>
                </div>
            </div>

            <!-- Infrastructure settings -->
            <h2 class="section-title" style="margin-top: 32px;">Infrastructure</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                Describe your deployment's infrastructure. These settings control which
                checks are run and how the report is generated.
            </p>

            <div class="feature-cards">
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.wire_managed_cluster" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Wire-Managed Cluster</span>
                        <span class="feature-card-desc">
                            Was the Kubernetes cluster deployed using Wire's ansible/kubespray tooling?
                            When enabled, we check for Wire deployment artifacts on the admin host.
                            When disabled, we assume the customer manages their own Kubernetes.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.has_internet" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Internet Access</span>
                        <span class="feature-card-desc">
                            Does this deployment have connectivity to the public internet during
                            operation? When enabled, we verify actual internet connectivity and
                            check AWS endpoints. When disabled, internet-dependent checks are skipped.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.has_dns" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">DNS Name Server</span>
                        <span class="feature-card-desc">
                            Does your network provide a DNS name server? In fully offline
                            deployments there may be no DNS. When disabled, DNS resolution
                            checks are skipped.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.users_access_externally" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Users Access Over Internet</span>
                        <span class="feature-card-desc">
                            Do end users connect to the Wire backend over the public internet
                            (rather than only from an internal network)? Affects how external
                            reachability issues are reported.
                        </span>
                    </div>
                </label>
            </div>

            <!-- Calling settings -->
            <h2 class="section-title" style="margin-top: 32px;">Calling</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                Configure calling (audio/video) settings for this deployment.
            </p>

            <div class="feature-cards">
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.expect_calling" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Calling Enabled</span>
                        <span class="feature-card-desc">
                            Is audio/video calling enabled for this deployment? When disabled,
                            all calling-related checks (TURN, SFT, coturn) are skipped.
                        </span>
                    </div>
                </label>
                <template v-if="setup.expect_calling">
                    <div class="feature-card">
                        <div class="feature-card-text" style="flex: 1;">
                            <span class="feature-card-label">Calling Type</span>
                            <span class="feature-card-desc">
                                On-prem: you run your own SFT and coturn servers.
                                Cloud: Wire provides cloud-hosted calling infrastructure.
                            </span>
                            <div style="margin-top: 8px;">
                                <SelectButton
                                    v-model="setup.calling_type"
                                    :options="calling_type_options"
                                    option-label="label"
                                    option-value="value"
                                    :allow-empty="false"
                                />
                            </div>
                        </div>
                    </div>
                    <label v-if="setup.calling_type === 'on_prem'" class="feature-card">
                        <ToggleSwitch v-model="setup.calling_in_dmz" />
                        <div class="feature-card-text">
                            <span class="feature-card-label">Calling in Separate DMZ Cluster</span>
                            <span class="feature-card-desc">
                                Are SFT and coturn running in a separate Kubernetes cluster
                                (DMZ) from the main Wire backend? If yes, you'll need to run the
                                gathering tool separately against each cluster.
                            </span>
                        </div>
                    </label>
                    <label v-if="setup.calling_type === 'on_prem'" class="feature-card">
                        <ToggleSwitch v-model="setup.expect_sft" />
                        <div class="feature-card-text">
                            <span class="feature-card-label">SFT (Conference Calling)</span>
                            <span class="feature-card-desc">
                                Selective Forwarding for group/conference calls. When enabled,
                                we check SFT pod health, node labels, and configuration.
                            </span>
                        </div>
                    </label>
                </template>
            </div>

            <!-- Federation settings -->
            <h2 class="section-title" style="margin-top: 32px;">Federation</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                Configure federation settings if this backend federates with other Wire backends.
            </p>

            <div class="feature-cards">
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.expect_federation" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Federation Enabled</span>
                        <span class="feature-card-desc">
                            Is this backend configured to federate with other Wire backends?
                            When enabled, we verify the full federation stack: enableFederation
                            in all services, federator pod, RabbitMQ, TLS certificates, DNS
                            SRV records, and federation strategy.
                        </span>
                    </div>
                </label>
            </div>

            <!-- Federation domains list -->
            <div v-if="setup.expect_federation" class="nodes-panel" style="margin-top: 12px;">
                <div class="nodes-panel-header">
                    <span class="nodes-panel-title">
                        <i class="pi pi-globe"></i>
                        Federation Partner Domains
                        <span class="nodes-count">{{ setup.federation_domains.length }}</span>
                    </span>
                    <Button
                        label="Add"
                        icon="pi pi-plus"
                        size="small"
                        severity="secondary"
                        outlined
                        @click="add_federation_domain"
                    />
                </div>
                <div v-if="setup.federation_domains.length === 0" class="nodes-empty">
                    No federation partner domains configured. Add domains of backends you federate with.
                </div>
                <div v-for="(domain, index) in setup.federation_domains" :key="index" class="node-row">
                    <div class="form-field" style="flex: 1; min-width: 0;">
                        <FloatLabel>
                            <InputText
                                :id="`federation_domain_${index}`"
                                :model-value="domain"
                                @update:model-value="(val: string) => update_federation_domain(index, val)"
                                :placeholder="`partner-${index + 1}.example.com`"
                                fluid
                            />
                            <label :for="`federation_domain_${index}`">Partner Domain {{ index + 1 }}</label>
                        </FloatLabel>
                    </div>
                    <button class="node-delete-btn" @click="remove_federation_domain(index)" title="Remove domain">
                        <i class="pi pi-times"></i>
                    </button>
                </div>
            </div>

            <!-- Features settings -->
            <h2 class="section-title" style="margin-top: 32px;">Features</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                Toggle optional features. The report skips warnings for features that aren't enabled.
            </p>

            <div class="feature-cards">
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.expect_metrics" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Monitoring Stack</span>
                        <span class="feature-card-desc">
                            Prometheus, Grafana, metrics-server. When enabled, we check that
                            monitoring components are deployed and the metrics API is reachable.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.expect_deeplink" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Mobile Deeplink</span>
                        <span class="feature-card-desc">
                            deeplink.json configuration for mobile client auto-discovery.
                            When enabled, we verify the deeplink JSON is served and contains
                            valid backend URLs.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.expect_sms" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">SMS Sending</span>
                        <span class="feature-card-desc">
                            Twilio or other SMS provider for phone verification. When enabled,
                            we check that the SMS configuration isn't using placeholder values.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.expect_legalhold" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Legal Hold (Secure Hold)</span>
                        <span class="feature-card-desc">
                            Records communications of specific users for compliance. When
                            enabled, we verify the galley feature flag and legalhold service.
                        </span>
                    </div>
                </label>
                <label class="feature-card">
                    <ToggleSwitch v-model="setup.using_ephemeral_databases" />
                    <div class="feature-card-text">
                        <span class="feature-card-label">Ephemeral Databases</span>
                        <span class="feature-card-desc">
                            Using databases-ephemeral / fake-aws (demo/test only). When enabled,
                            suppresses warnings about non-production database usage.
                        </span>
                    </div>
                </label>
            </div>

            <!-- Node configuration section -->
            <h2 class="section-title" style="margin-top: 32px;">Nodes</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                Configure the IP addresses of each cluster node. When provided, these override
                dynamic discovery - the runner will use exactly these hosts instead of querying
                kubectl or inferring nodes from database IPs. Results are named
                <code>kubenode-{ip}</code> and <code>datanode-{ip}</code>.
                <span v-if="hostfile_parsed" class="prefill-note">
                    Pre-filled from your host file.
                </span>
            </p>

            <div class="nodes-columns">
                <!-- Kubernetes nodes -->
                <div class="nodes-panel">
                    <div class="nodes-panel-header">
                        <span class="nodes-panel-title">
                            <i class="pi pi-server"></i>
                            Kube Nodes
                            <span class="nodes-count">{{ setup.kube_nodes.length }}</span>
                        </span>
                        <Button
                            label="Add"
                            icon="pi pi-plus"
                            size="small"
                            severity="secondary"
                            outlined
                            @click="add_kube_node"
                        />
                    </div>
                    <div v-if="setup.kube_nodes.length === 0" class="nodes-empty">
                        No kube nodes configured. Add IPs or import a host file.
                    </div>
                    <div v-for="(ip, index) in setup.kube_nodes" :key="index" class="node-row">
                        <IpInput
                            :model-value="ip"
                            @update:model-value="(val: string) => update_kube_node(index, val)"
                            :label="`Kube Node ${index + 1}`"
                            :placeholder="`10.0.0.${index + 1}`"
                            :input-id="`kube_node_${index}`"
                        />
                        <button class="node-delete-btn" @click="remove_kube_node(index)" title="Remove node">
                            <i class="pi pi-times"></i>
                        </button>
                    </div>
                </div>

                <!-- Data nodes -->
                <div class="nodes-panel">
                    <div class="nodes-panel-header">
                        <span class="nodes-panel-title">
                            <i class="pi pi-database"></i>
                            Data Nodes
                            <span class="nodes-count">{{ setup.data_nodes.length }}</span>
                        </span>
                        <Button
                            label="Add"
                            icon="pi pi-plus"
                            size="small"
                            severity="secondary"
                            outlined
                            @click="add_data_node"
                        />
                    </div>
                    <div v-if="setup.data_nodes.length === 0" class="nodes-empty">
                        No data nodes configured. Add IPs or import a host file.
                    </div>
                    <div v-for="(ip, index) in setup.data_nodes" :key="index" class="node-row">
                        <IpInput
                            :model-value="ip"
                            @update:model-value="(val: string) => update_data_node(index, val)"
                            :label="`Data Node ${index + 1}`"
                            :placeholder="`10.0.1.${index + 1}`"
                            :input-id="`data_node_${index}`"
                        />
                        <button class="node-delete-btn" @click="remove_data_node(index)" title="Remove node">
                            <i class="pi pi-times"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>

            <!-- Kubeconfig paths -->
            <h2 class="section-title" style="margin-top: 32px;">Kubeconfig</h2>
            <p class="step-description" style="margin-bottom: 16px;">
                Path to the kubeconfig file on the admin host. If left at the default,
                the runner will use its standard discovery. Only change this if your
                kubeconfig is in a non-standard location.
            </p>

            <div class="form-grid">
                <div class="form-field">
                    <FloatLabel>
                        <InputText
                            id="kubeconfig_path"
                            v-model="setup.kubeconfig_path"
                            placeholder="~/.kube/config"
                            fluid
                        />
                        <label for="kubeconfig_path">
                            {{ setup.calling_in_dmz ? 'Main Cluster Kubeconfig' : 'Kubeconfig Path' }}
                        </label>
                    </FloatLabel>
                </div>
                <div v-if="setup.calling_in_dmz" class="form-field">
                    <FloatLabel>
                        <InputText
                            id="calling_kubeconfig_path"
                            v-model="setup.calling_kubeconfig_path"
                            placeholder="/path/to/calling-kubeconfig"
                            fluid
                        />
                        <label for="calling_kubeconfig_path">Calling DMZ Cluster Kubeconfig</label>
                    </FloatLabel>
                </div>
            </div>

        <div class="step-actions">
            <Button label="Back" severity="secondary" icon="pi pi-arrow-left" @click="$emit('back')" />
            <Button label="Next" icon="pi pi-arrow-right" icon-pos="right" @click="validate_and_next" />
        </div>
    </div>
</template>

<script setup lang="ts">
// External
import { ref } from 'vue'
import InputText from 'primevue/inputtext'
import FloatLabel from 'primevue/floatlabel'
import Button from 'primevue/button'
import ToggleSwitch from 'primevue/toggleswitch'
import SelectButton from 'primevue/selectbutton'
import { useToast } from 'primevue/usetoast'
// Ours
import type { SetupData } from '../lib/settings_yaml'
import IpInput from './IpInput.vue'

// Two-way binding for the whole setup object parent passes v-model:setup="setup"
const setup = defineModel<SetupData>('setup', { required: true })

// Options for the calling type SelectButton
const calling_type_options = [
    { label: 'On-Premises',       value: 'on_prem' },
    { label: 'Cloud (Wire-hosted)', value: 'cloud' },
]

// Whether a host file was already parsed shows the pre-fill note in the template
const { hostfile_parsed } = defineProps<{
    hostfile_parsed: boolean
}>()

const emit = defineEmits<{
    // User clicked the Back button
    back: []
    // User clicked the Next button
    next: []
}>()

const toast = useToast()

// Tracks which required fields failed validation so we can highlight them
const validation_errors = ref<Set<string>>(new Set())

// Extracts only the keys of SetupData whose values are strings, so the
// compiler rejects adding a non-string field to REQUIRED_FIELDS
type StringKeysOf<T> = { [K in keyof T]: T[K] extends string ? K : never }[keyof T]

// Fields that must be filled before proceeding - leaving these empty causes
// the settings YAML to silently use placeholder IPs/domains, which could
// point the gatherer at the wrong machine
const REQUIRED_FIELDS: { key: StringKeysOf<SetupData>; label: string }[] = [
    { key: 'admin_host_ip',  label: 'Admin Host IP' },
    { key: 'cluster_domain', label: 'Cluster Domain' },
    { key: 'k8s_namespace',  label: 'Kubernetes Namespace' },
]

// Validates required fields are non-empty before letting the user proceed
function validate_and_next(): void {
    const missing: string[] = []
    const errors  = new Set<string>()

    for (const field of REQUIRED_FIELDS) {
        // StringKeysOf<SetupData> guarantees field.key refers to a string property
        const value = setup.value[field.key]
        if (value.trim() === '') {
            missing.push(field.label)
            errors.add(field.key)
        }
    }

    validation_errors.value = errors

    if (missing.length > 0) {
        toast.add({
            severity: 'warn',
            summary:  'Required fields missing',
            detail:   `Please fill in: ${missing.join(', ')}`,
            life:     5000,
        })
        return
    }

    emit('next')
}

// -- Node management helpers for kube nodes --

// Append a blank entry so the user can type a new IP
function add_kube_node() {
    setup.value.kube_nodes = [...setup.value.kube_nodes, '']
}

// Drop the node at the given index
function remove_kube_node(index: number) {
    setup.value.kube_nodes = setup.value.kube_nodes.filter((_, i) => i !== index)
}

// Replace the IP at the given index with the new value
function update_kube_node(index: number, value: string) {
    const updated = [...setup.value.kube_nodes]
    updated[index] = value
    setup.value.kube_nodes = updated
}

// -- Node management helpers for data nodes --

// Append a blank entry so the user can type a new IP
function add_data_node() {
    setup.value.data_nodes = [...setup.value.data_nodes, '']
}

// Drop the node at the given index
function remove_data_node(index: number) {
    setup.value.data_nodes = setup.value.data_nodes.filter((_, i) => i !== index)
}

// Replace the IP at the given index with the new value
function update_data_node(index: number, value: string) {
    const updated = [...setup.value.data_nodes]
    updated[index] = value
    setup.value.data_nodes = updated
}

// -- Federation domain helpers --

// Append a blank entry for a new federation partner domain
function add_federation_domain() {
    setup.value.federation_domains = [...setup.value.federation_domains, '']
}

// Drop the domain at the given index
function remove_federation_domain(index: number) {
    setup.value.federation_domains = setup.value.federation_domains.filter((_, i) => i !== index)
}

// Replace the domain at the given index with the new value
function update_federation_domain(index: number, value: string) {
    const updated = [...setup.value.federation_domains]
    updated[index] = value
    setup.value.federation_domains = updated
}
</script>

<style scoped>
/* Step wrapper with fade-in animation that matches the other step panels */
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

/* Shown when the form was pre-filled from an imported host file */
.prefill-note {
    display: block;
    margin-top: 4px;
    color: var(--wire-green);
    font-weight: 500;
}

/* Section headings inside the form */
.section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--wire-dark-gray);
    margin-bottom: 16px;
}

/* Two-column responsive grid for form fields */
.form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
}

@media (max-width: 640px) {
    .form-grid {
        grid-template-columns: 1fr;
    }
}

.form-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

/* Feature flags grid - two-column layout matching the form grid */
.feature-flags {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}

@media (max-width: 640px) {
    .feature-flags {
        grid-template-columns: 1fr;
    }
}

.feature-flag {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
}

.feature-flag:hover {
    border-color: var(--wire-blue);
}

.feature-flag-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.feature-flag-label {
    font-size: 14px;
    font-weight: 500;
    color: var(--wire-dark-gray);
}

.feature-flag-hint {
    font-size: 12px;
    color: var(--wire-medium-gray);
}

/* Full-width feature cards (new layout for site-survey settings) */
.feature-cards {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.feature-card {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    padding: 14px 18px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
}

.feature-card:hover {
    border-color: var(--wire-blue);
}

.feature-card-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    min-width: 0;
}

.feature-card-label {
    font-size: 14px;
    font-weight: 600;
    color: var(--wire-dark-gray);
}

.feature-card-desc {
    font-size: 13px;
    color: var(--wire-medium-gray);
    line-height: 1.5;
}

/* Side-by-side layout for kube and data node panels */
.nodes-columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-top: 8px;
}

@media (max-width: 700px) {
    .nodes-columns {
        grid-template-columns: 1fr;
    }
}

.nodes-panel {
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    padding: 16px;
    background: var(--wire-white);
}

.nodes-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
}

.nodes-panel-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    font-weight: 600;
    color: var(--wire-dark-gray);
}

/* Blue pill badge showing the node count */
.nodes-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: 10px;
    background: var(--wire-blue);
    color: white;
    font-size: 11px;
    font-weight: 700;
}

.nodes-empty {
    font-size: 13px;
    color: var(--wire-medium-gray);
    font-style: italic;
    padding: 8px 0;
}

/* Each IP-input row with inline delete button */
.node-row {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    margin-bottom: 10px;
}

.node-row > :first-child {
    flex: 1;
    min-width: 0;
}

/* Small ghost button that removes the node on click */
.node-delete-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 6px;
    background: var(--wire-white);
    color: var(--wire-medium-gray);
    cursor: pointer;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
    margin-bottom: 2px;
}

.node-delete-btn:hover {
    background: #fef2f2;
    color: #dc2626;
    border-color: #fca5a5;
}

</style>
