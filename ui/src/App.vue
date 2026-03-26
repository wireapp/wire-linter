<template>
    <Toast />
    <div class="app-root">
        <!-- Header -->
        <header class="app-header">
            <div class="header-content">
                <div class="header-logo">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="11" stroke="#0667C8" stroke-width="2" />
                        <path d="M7 12l3 3 7-7" stroke="#0667C8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <span class="header-title">Wire Fact Gathering Tool</span>
                </div>
            </div>
        </header>

        <!-- Main content and stepper -->
        <main class="app-main">
            <div class="step-container">
                <Stepper v-model:value="active_step">
                    <StepList>
                        <Step value="1">Host File</Step>
                        <Step value="2">Configuration</Step>
                        <Step value="3">Settings File</Step>
                        <Step value="4">Run Tool</Step>
                        <Step value="5">Upload Results</Step>
                        <Step value="6">Report</Step>
                    </StepList>

                    <StepPanels>
                        <!-- STEP 1: Host File Import (optional) -->
                        <StepPanel v-slot="{ activateCallback }" value="1">
                            <HostFileStep
                                @parsed="on_hosts_parsed"
                                @next="activateCallback('2')"
                            />
                        </StepPanel>

                        <!-- STEP 2: Configuration - Connection details form -->
                        <StepPanel v-slot="{ activateCallback }" value="2">
                            <ConfigurationStep
                                v-model:setup="setup"
                                :hostfile_parsed="hostfile_parsed"
                                @back="activateCallback('1')"
                                @next="activateCallback('3')"
                            />
                        </StepPanel>

                        <!-- STEP 3: Settings File - Generated YAML -->
                        <StepPanel v-slot="{ activateCallback }" value="3">
                            <SettingsFileStep
                                :setup="setup"
                                @back="activateCallback('2')"
                                @next="activateCallback('4')"
                            />
                        </StepPanel>

                        <!-- STEP 4: Run Tool - Commands -->
                        <StepPanel v-slot="{ activateCallback }" value="4">
                            <RunToolStep
                                :setup="setup"
                                @back="activateCallback('3')"
                                @next="activateCallback('5')"
                            />
                        </StepPanel>

                        <!-- STEP 5: Upload Results -->
                        <StepPanel v-slot="{ activateCallback }" value="5">
                            <UploadStep
                                :setup="setup"
                                @back="activateCallback('4')"
                                @analyze="(raw_text) => analyze_data(raw_text, activateCallback)"
                            />
                        </StepPanel>

                        <!-- STEP 6: Report -->
                        <StepPanel v-slot="{ activateCallback }" value="6">
                            <ReportStep
                                ref="report_step_ref"
                                :results="results"
                                :data_points_list="data_points_list"
                                :gathering_config="gathering_config"
                                @back="activateCallback('5')"
                            />
                        </StepPanel>
                    </StepPanels>
                </Stepper>
            </div>
        </main>
    </div>
</template>

<script setup lang="ts">
// External
import { ref } from 'vue'
import Toast from 'primevue/toast'
import Stepper from 'primevue/stepper'
import StepList from 'primevue/steplist'
import StepPanels from 'primevue/steppanels'
import Step from 'primevue/step'
import StepPanel from 'primevue/steppanel'
// Ours
import HostFileStep from './components/HostFileStep.vue'
import ConfigurationStep from './components/ConfigurationStep.vue'
import UploadStep from './components/UploadStep.vue'
import SettingsFileStep from './components/SettingsFileStep.vue'
import RunToolStep from './components/RunToolStep.vue'
import ReportStep from './components/ReportStep.vue'
import type { SetupData } from './lib/settings_yaml'
import type { ParsedHosts } from './lib/hostfile_types'
import { apply_parsed_hosts_to_setup } from './lib/hostfile_parser'
import { use_analysis } from './composables/use_analysis'

// -- State --

// Stepper tracks the active step as a string value
const active_step = ref('1')

// Step 1: Whether a host file has been parsed (gates the pre-fill note in steps 2-3)
const hostfile_parsed   = ref(false)

// Step 2: Setup form fields defaults are from the demo deployment at robot-takeover.com.
// NOTE (INTENTIONAL - NOT A BUG): ssh_key_path intentionally points to the developer's
// local key (/home/arthur/...) because the SSH key used to connect to the demo server lives
// on the local machine, not on the remote host. This is correct: the runner initiates the
// SSH connection from the operator's workstation. All defaults here are specific to the demo
// environment and are meant to be overwritten by the operator during setup.
// By contrast, db_ssh_key is a path on the admin host (jump host) because the runner SSHes
// to admin first, then uses that key to reach DB VMs.
const setup = ref<SetupData>({
    admin_host_ip:      'robot-takeover.com',
    admin_user:         'demo',
    cluster_domain:     'robot-takeover.com',
    k8s_namespace:      'default',
    cassandra_host:     '192.168.122.220',
    elasticsearch_host: '192.168.122.220',
    minio_host:         '192.168.122.220',
    postgres_host:      '192.168.122.220',
    rabbitmq_host:      '192.168.122.220',
    ssh_key_path:       '/home/arthur/.ssh/id_ed25519',  // local machine key (see note above)
    ssh_port:           '22',
    // SSH credentials for reaching database VMs from the admin host (jump host scenario).
    // When set, the runner SSHes to admin host first, then from there to the DB host.
    db_ssh_user:        'demo',
    db_ssh_key:         '/home/demo/wire-server-deploy/ssh/id_ed25519',  // remote admin host key
    // Explicit node IP lists pre-filled from host file when available.
    // When non-empty these override dynamic host discovery in the runner.
    kube_nodes:         [] as string[],
    data_nodes:         [] as string[],
    // Deployment feature flags tell checkers what to expect
    expect_metrics:             false,
    expect_sso:                 false,
    expect_deeplink:            false,
    expect_sms:                 false,
    expect_sft:                 false,
    using_ephemeral_databases:  false,
    // Site-survey-derived flags
    wire_managed_cluster:       true,
    has_internet:               true,
    has_dns:                    true,
    users_access_externally:    true,
    expect_calling:             true,
    calling_type:               'on_prem',
    calling_in_dmz:             false,
    expect_federation:          false,
    federation_domains:         [] as string[],
    expect_legalhold:           false,
    // Kubeconfig paths — used in Step 4 commands, not saved to YAML.
    // Default is the Wire-managed kubespray location. ~/.kube/config is
    // typically empty on Wire admin hosts — the real kubeconfig lives inside
    // wire-server-deploy. If the user doesn't change this, Step 4 omits the
    // --kubeconfig flag (the runner's Docker wrapper finds it automatically).
    kubeconfig_path:            '~/wire-server-deploy/ansible/inventory/kubeconfig.dec',
    calling_kubeconfig_path:    '',
})

// Template ref for ReportStep used by the analysis composable to expand trees after loading
const report_step_ref = ref<InstanceType<typeof ReportStep> | null>(null)

// Step 6: Analysis pipeline parsing, checking, and results management
const { results, data_points_list, gathering_config, analyze_data } = use_analysis({ report_step_ref })

// -- Methods --

// Receive parsed host data from HostFileStep, apply it to the setup form, mark it as parsed
function on_hosts_parsed(hosts: ParsedHosts): void {
    apply_parsed_hosts_to_setup(hosts, setup.value)
    hostfile_parsed.value = true
}
</script>

<style scoped>
.app-root {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
}

/* Header */
.app-header {
    background: var(--wire-white);
    border-bottom: 1px solid var(--wire-border-gray);
    padding: 0 24px;
    height: 56px;
    display: flex;
    align-items: center;
    flex-shrink: 0;
}

.header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}

.header-logo {
    display: flex;
    align-items: center;
    gap: 10px;
}

.header-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--wire-dark-gray);
}

/* Main */
.app-main {
    flex: 1;
    overflow-y: auto;
    padding: 32px 24px;
}

.step-container {
    max-width: 1000px;
    margin: 0 auto;
}

.step-content {
    animation: fade-in 0.3s ease;
}

@keyframes fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
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

/* Command labels */
.command-label {
    font-size: 14px;
    font-weight: 500;
    color: var(--wire-dark-gray);
    margin-bottom: 8px;
}

/* Right-aligned step actions with multiple buttons */
.step-actions-right {
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Results */
.results-step .step-title {
    margin-bottom: 8px;
}

/* Navigation buttons at bottom of each step */
.step-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 32px;
    padding-top: 24px;
    border-top: 1px solid var(--wire-border-gray);
}

/* ── Responsive ─────────────────────────────────────────────────────── */

/* Responsive */
@media (max-width: 768px) {
    .app-main {
        padding: 20px 16px;
    }

    .step-title {
        font-size: 22px;
    }

    .parsed-summary {
        grid-template-columns: 1fr;
    }
}
</style>
