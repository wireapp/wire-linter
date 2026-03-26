<!--
    ConfigTab.vue - Displays the gathering config embedded in the JSONL file.

    Shows the settings that were used to produce this particular data set,
    organized into sections: admin host, cluster, databases, kubernetes,
    options, and nodes.

    Props:
      - config: GatheringConfig | null - the parsed config from the JSONL header
-->
<template>
    <div class="config-tab">
        <div v-if="!config" class="config-empty">
            <i class="pi pi-info-circle" style="font-size: 24px; color: var(--wire-medium-gray);"></i>
            <p>No configuration data found in this JSONL file.</p>
            <p class="config-empty-hint">
                Older JSONL files do not include a config header. Re-run the
                gatherer to produce a file with embedded configuration.
            </p>
        </div>

        <template v-else>
            <!-- Admin Host -->
            <div class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-server"></i>
                    Admin Host
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr>
                            <td class="config-key">IP / Hostname</td>
                            <td class="config-value"><code>{{ config.admin_host.ip }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">User</td>
                            <td class="config-value"><code>{{ config.admin_host.user }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">SSH Key</td>
                            <td class="config-value"><code>{{ config.admin_host.ssh_key || '(default)' }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">SSH Port</td>
                            <td class="config-value"><code>{{ config.admin_host.ssh_port }}</code></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Cluster -->
            <div class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-globe"></i>
                    Cluster
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr>
                            <td class="config-key">Domain</td>
                            <td class="config-value"><code>{{ config.cluster.domain }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">Kubernetes Namespace</td>
                            <td class="config-value"><code>{{ config.cluster.kubernetes_namespace }}</code></td>
                        </tr>
                        <tr v-if="config.wire_domain && config.wire_domain !== config.cluster.domain">
                            <td class="config-key">Wire Domain</td>
                            <td class="config-value"><code>{{ config.wire_domain }}</code></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Databases -->
            <div class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-database"></i>
                    Databases
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr>
                            <td class="config-key">Cassandra</td>
                            <td class="config-value"><code>{{ config.databases.cassandra }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">Elasticsearch</td>
                            <td class="config-value"><code>{{ config.databases.elasticsearch }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">MinIO</td>
                            <td class="config-value"><code>{{ config.databases.minio }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">PostgreSQL</td>
                            <td class="config-value"><code>{{ config.databases.postgresql }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">RabbitMQ</td>
                            <td class="config-value"><code>{{ config.databases.rabbitmq }}</code></td>
                        </tr>
                        <tr v-if="config.databases.ssh_user">
                            <td class="config-key">DB SSH User</td>
                            <td class="config-value"><code>{{ config.databases.ssh_user }}</code></td>
                        </tr>
                        <tr v-if="config.databases.ssh_key">
                            <td class="config-key">DB SSH Key</td>
                            <td class="config-value"><code>{{ config.databases.ssh_key }}</code></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Kubernetes -->
            <div class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-box"></i>
                    Kubernetes
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr>
                            <td class="config-key">Docker Image</td>
                            <td class="config-value"><code>{{ config.kubernetes.docker_image || '(none - direct kubectl)' }}</code></td>
                        </tr>
                        <tr v-if="config.kubernetes_context">
                            <td class="config-key">Context</td>
                            <td class="config-value"><code>{{ config.kubernetes_context }}</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">Admin Home</td>
                            <td class="config-value"><code>{{ config.kubernetes.admin_home }}</code></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Gathering Options -->
            <div class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-cog"></i>
                    Options
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr>
                            <td class="config-key">Gathered From</td>
                            <td class="config-value">
                                <span class="config-badge" :class="config.gathered_from === 'external' ? 'badge-blue' : 'badge-green'">
                                    {{ config.gathered_from }}
                                </span>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">Timeout</td>
                            <td class="config-value"><code>{{ config.timeout }}s</code></td>
                        </tr>
                        <tr>
                            <td class="config-key">Check Kubernetes</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.check_kubernetes ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">Check Databases</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.check_databases ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">Check Network</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.check_network ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">Check Wire Services</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.check_wire_services ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Deployment Feature Flags -->
            <div class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-sliders-h"></i>
                    Deployment Features
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr>
                            <td class="config-key">Metrics / Monitoring</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.expect_metrics ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">SSO (SAML / SCIM)</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.expect_sso ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">Mobile Deeplink</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.expect_deeplink ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">SMS Sending</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.expect_sms ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">SFT (Calling)</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.expect_sft ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                        <tr>
                            <td class="config-key">Ephemeral Databases</td>
                            <td class="config-value">
                                <i class="pi" :class="config.options.using_ephemeral_databases ? 'pi-check-circle config-check-on' : 'pi-times-circle config-check-off'"></i>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Nodes (only show if any are configured) -->
            <div v-if="has_explicit_nodes" class="config-section">
                <h3 class="config-section-title">
                    <i class="pi pi-sitemap"></i>
                    Explicit Nodes
                </h3>
                <table class="config-table">
                    <tbody>
                        <tr v-if="config.nodes?.kube_nodes?.length > 0">
                            <td class="config-key">Kube Nodes</td>
                            <td class="config-value">
                                <code v-for="(ip, index) in config.nodes.kube_nodes" :key="ip" class="config-ip">
                                    {{ ip }}<span v-if="index < config.nodes.kube_nodes.length - 1">, </span>
                                </code>
                            </td>
                        </tr>
                        <tr v-if="config.nodes?.data_nodes?.length > 0">
                            <td class="config-key">Data Nodes</td>
                            <td class="config-value">
                                <code v-for="(ip, index) in config.nodes.data_nodes" :key="ip" class="config-ip">
                                    {{ ip }}<span v-if="index < config.nodes.data_nodes.length - 1">, </span>
                                </code>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
// External
import { computed } from 'vue'

// Ours
import type { GatheringConfig } from '../sample-data'

const props = defineProps<{
    config: GatheringConfig | null
}>()

// Only show the Nodes section when at least one list has entries
const has_explicit_nodes = computed((): boolean => {
    if (!props.config?.nodes) return false
    return (props.config.nodes.kube_nodes?.length ?? 0) > 0
        || (props.config.nodes.data_nodes?.length ?? 0) > 0
})
</script>

<style scoped>
.config-tab {
    max-width: 700px;
}

/* Empty state - matches PortsTab empty style */
.config-empty {
    text-align: center;
    padding: 48px 24px;
    color: var(--wire-medium-gray);
}

.config-empty p {
    margin: 8px 0;
}

.config-empty-hint {
    font-size: 13px;
    opacity: 0.8;
}

/* Section cards */
.config-section {
    margin-bottom: 20px;
    border: 1px solid var(--wire-border-gray);
    border-radius: 8px;
    overflow: hidden;
}

.config-section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--wire-dark-gray);
    background: var(--wire-light-gray);
    border-bottom: 1px solid var(--wire-border-gray);
}

/* Key-value table */
.config-table {
    width: 100%;
    border-collapse: collapse;
}

.config-table tr:not(:last-child) {
    border-bottom: 1px solid var(--wire-border-gray);
}

.config-key {
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 500;
    color: var(--wire-medium-gray);
    white-space: nowrap;
    width: 180px;
}

.config-value {
    padding: 10px 16px;
    font-size: 13px;
    color: var(--wire-dark-gray);
}

.config-value code {
    background: var(--wire-light-gray);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
}

/* Gathered-from badge */
.config-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
}

.badge-blue {
    background: rgba(6, 103, 200, 0.12);
    color: var(--wire-blue);
}

.badge-green {
    background: rgba(34, 139, 34, 0.12);
    color: #228b22;
}

/* Check option icons */
.config-check-on {
    color: #228b22;
    font-size: 16px;
}

.config-check-off {
    color: var(--wire-medium-gray);
    font-size: 16px;
}
</style>
