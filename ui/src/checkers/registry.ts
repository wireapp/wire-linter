/**
 * Checker registry: collects all foundation checkers and provides
 * the main run_checks() function that replaces the old lint_data().
 *
 * Since this runs in the browser (no filesystem scanning), all
 * checkers are explicitly imported and instantiated here. Default imports
 * with aliases prevent class name collisions across categories.
 */

// Ours
import type { DataPoint, GatheringConfig } from '../sample-data'
import type { CheckOutput } from './base_checker'
import { type BaseChecker } from './base_checker'
import { DataLookup } from './data_lookup'
import { render_template } from '../lib/template_engine'

// Host / Admin machine (7)
import HostDiskUsage from './host_admin/disk_usage'
import HostMemoryUsage from './host_admin/memory_usage'
import HostCpuCount from './host_admin/cpu_count'
import HostLoadAverage from './host_admin/load_average'
import HostUptime from './host_admin/uptime'
import HostNtpSynchronized from './host_admin/ntp_synchronized'
import HostNtpOffset from './host_admin/ntp_offset'

// OS / System (3)
import OsVersionMatches from './os/version_matches'
import KubenodeNtp from './os/kubenode_ntp'
import UnprivilegedPortStart from './os/unprivileged_port_start'

// VMs (3)
import VmDiskUsage from './vm/disk_usage'
import VmMemoryUsage from './vm/memory_usage'
import VmLoadAverage from './vm/load_average'

// DNS (2)
import DnsSubdomainResolution from './dns/subdomain_resolution'
import EmailDnsRecords from './dns/email_dns_records'

// TLS / Certificates (4)
import TlsCertificateExpiration from './tls/certificate_expiration'
import TlsChainValidity from './tls/chain_validity'
import KubeadmCertExpiration from './tls/kubeadm_cert_expiration'
import OpensearchCertKeyUsage from './tls/opensearch_cert_key_usage'

// Kubernetes (35)
import K8sNodeCount from './kubernetes/node_count'
import AllNodesReady from './kubernetes/all_nodes_ready'
import K8sVersion from './kubernetes/k8s_version'
import ContainerRuntime from './kubernetes/container_runtime'
import UnhealthyPods from './kubernetes/unhealthy_pods'
import TotalRunningPods from './kubernetes/total_running_pods'
import CertificatesReady from './kubernetes/certificates_ready'
import CertificateCount from './kubernetes/certificate_count'
import IngressResources from './kubernetes/ingress_resources'
import MetricsApi from './kubernetes/metrics_api'
import RestartCounts from './kubernetes/restart_counts'
import PvcStatus from './kubernetes/pvc_status'
import HelmChartVersions from './kubernetes/helm_chart_versions'
import EtcdHealth from './kubernetes/etcd_health'
import SftNodeLabels from './kubernetes/sft_node_labels'
import CoturnMemoryLimits from './kubernetes/coturn_memory_limits'
import ConfigmapStaleness from './kubernetes/configmap_staleness'
import CoreDnsHealth from './kubernetes/coredns_health'
import CronJobHealth from './kubernetes/cronjob_health'
import DisruptionBudgets from './kubernetes/disruption_budgets'
import HpaConfiguration from './kubernetes/hpa_configuration'
import ImageConsistency from './kubernetes/image_consistency'
import ImagePullPolicy from './kubernetes/image_pull_policy'
import IngressTls from './kubernetes/ingress_tls'
import NodePressure from './kubernetes/node_pressure'
import PodAntiAffinity from './kubernetes/pod_anti_affinity'
import ProbeConfiguration from './kubernetes/probe_configuration'
import ReplicaCount from './kubernetes/replica_count'
import ResourceLimits from './kubernetes/resource_limits'
import ResourceQuotas from './kubernetes/resource_quotas'
import SchedulingFailures from './kubernetes/scheduling_failures'
import SecurityContext from './kubernetes/security_context'
import ServiceEndpoints from './kubernetes/service_endpoints'
import StuckRollouts from './kubernetes/stuck_rollouts'
import WarningEvents from './kubernetes/warning_events'

// Data / Cassandra (7)
import CassandraClusterStatus from './cassandra/cluster_status'
import CassandraNodeCount from './cassandra/node_count'
import CassandraNtpSynchronized from './cassandra/ntp_synchronized'
import CassandraDataDiskUsage from './cassandra/data_disk_usage'
import CassandraKeyspaces from './cassandra/keyspaces'
import CassandraSparTables from './cassandra/spar_tables'
import CassandraSparIdpCount from './cassandra/spar_idp_count'

// Data / Elasticsearch (4)
import EsClusterHealth from './elasticsearch/cluster_health'
import EsNodeCount from './elasticsearch/node_count'
import EsShardCount from './elasticsearch/shard_count'
import EsReadOnlyMode from './elasticsearch/read_only_mode'

// Data / PostgreSQL (4)
import PgReplicationStatus from './postgresql/replication_status'
import PgNodeCount from './postgresql/node_count'
import PgVersion from './postgresql/version'
import PgReplicationLag from './postgresql/replication_lag'

// Data / MinIO (5)
import MinioNetworkStatus from './minio/network_status'
import MinioDrivesStatus from './minio/drives_status'
import MinioBucketCount from './minio/bucket_count'
import MinioVersion from './minio/version'
import MinioErasureHealth from './minio/erasure_health'

// Data / RabbitMQ (6)
import RmqClusterStatus from './rabbitmq/cluster_status'
import RmqNodeCount from './rabbitmq/node_count'
import RmqVersion from './rabbitmq/version'
import RmqQueueDepth from './rabbitmq/queue_depth'
import RmqAlarms from './rabbitmq/alarms'
import RmqQueuePersistence from './rabbitmq/queue_persistence'

// Data / Redis (3)
import RedisPodStatus from './redis/pod_status'
import RedisMemoryEviction from './redis/memory_eviction'
import RedisMaxmemoryConfigured from './redis/maxmemory_configured'

// Wire Services (18)
import BrigHealth from './wire_services/brig'
import GalleyHealth from './wire_services/galley'
import CannonHealth from './wire_services/cannon'
import CargoholdHealth from './wire_services/cargohold'
import GundeckHealth from './wire_services/gundeck'
import SparHealth from './wire_services/spar'
import NginzHealth from './wire_services/nginz'
import BackgroundWorkerHealth from './wire_services/background_worker'
import SftdHealth from './wire_services/sftd'
import CoturnHealth from './wire_services/coturn'
import WebappHealth from './wire_services/webapp'
import TeamSettingsHealth from './wire_services/team_settings'
import AccountPagesHealth from './wire_services/account_pages'
import HelmReleases from './wire_services/helm_releases'
import StatusEndpoints from './wire_services/status_endpoints'
import WebappHttp from './wire_services/webapp_http'
import IngressResponse from './wire_services/ingress_response'
import AssetHost from './wire_services/asset_host'

// Networking / Calling (3)
import PortReachability from './networking/port_reachability'
import TurnConnectivity from './networking/turn_connectivity'
import SftdReachable from './networking/sftd_reachable'

// Networking / Ports (1)
import PortConnectivity from './networking/port_connectivity'

// Federation / MLS (2)
import FederationDomainConsistency from './federation/domain_consistency'
import BrigFederationDomain from './federation/brig_domain_matches_cluster'

// MLS / Protocol (1)
import MlsReadiness from './mls/readiness'

// Helm / Config Validation (10)
import CassandraReplication from './helm_config/cassandra_replication'
import GalleyFeatureFlags from './helm_config/galley_feature_flags'
import WebappBackendUrls from './helm_config/webapp_backend_urls'
import IsSelfHosted from './helm_config/is_self_hosted'
import DeeplinkJson from './helm_config/deeplink_json'
import DatabaseHostConsistency from './helm_config/database_host_consistency'
import ServiceLogLevels from './helm_config/service_log_levels'
import BrigSmsPlaceholder from './helm_config/brig_sms_placeholder'
import BrigSmtpSecurity from './helm_config/brig_smtp_security'
import IngressProxyProtocol from './helm_config/ingress_proxy_protocol'

// Site-survey: auto-detected settings
import PushNotificationMode from './helm_config/push_notification_mode'
import RegistrationReport from './helm_config/registration_report'
import SsoStatusReport from './helm_config/sso_status_report'
import BrigEmailServiceMatch from './helm_config/brig_email_service_match'
import FederationEnablement from './helm_config/federation_enablement'

// Site-survey: user-declared settings
import CallingConfiguration from './helm_config/calling_configuration'
import TurnUrisValid from './helm_config/turn_uris_valid'
import LegalholdConfiguration from './helm_config/legalhold_configuration'

// Site-survey: federation
import FederationStrategy from './helm_config/federation_strategy'
import FederationRabbitmq from './helm_config/federation_rabbitmq'
import FederationCallingBrig from './helm_config/federation_calling_brig'
import FederationCallingSft from './helm_config/federation_calling_sft'
import FederationCallingCoturn from './helm_config/federation_calling_coturn'
import FederationTlsCerts from './tls/federation_tls_certs'
import FederationSrvRecords from './dns/federation_srv_records'
import FederatorChecker from './wire_services/federator'

// Site-survey: networking and infrastructure
import InternetConnectivity from './networking/internet_connectivity'
import AwsSnsReachable from './networking/aws_sns_reachable'
import AwsSqsReachable from './networking/aws_sqs_reachable'
import WireDeployDirectory from './operations/wire_deploy_directory'
import ImagePullIssues from './kubernetes/image_pull_issues'
import NodeImageConsistency from './kubernetes/node_image_consistency'
import LdapScimBridge from './wire_services/ldap_scim_bridge'

// Client-mode checkers (--source client)
import ClientDnsResolution from './client/dns_resolution'
import ClientTlsValidity from './client/tls_validity'
import ClientWebappReachable from './client/webapp_reachable'
import ClientApiReachable from './client/api_reachable'
import ClientWebsocketReachable from './client/websocket_reachable'
import ClientCallingReachable from './client/calling_reachable'
import ClientDeeplinkJson from './client/deeplink_json'
import ClientFederationReachable from './client/federation_reachable'

// Secrets / Credentials (1)
import SecretsRequiredPresent from './secrets/required_present'

// Upgrades / Migrations (5)
import MigrationJobs from './upgrades/migration_jobs'
import HelmReleaseStatus from './upgrades/helm_release_status'
import CertmanagerTestMode from './upgrades/certmanager_test_mode'
import VersionCurrency from './upgrades/version_currency'
import EphemeralInProduction from './upgrades/ephemeral_in_production'

// Security / Hardening (3)
import SternNotExposed from './security/stern_not_exposed'
import InternalEndpoints from './security/internal_endpoints'
import RabbitmqDefaultCredentials from './security/rabbitmq_default_credentials'

// Operations / Tooling (4)
import LogRotation from './operations/log_rotation'
import BackupFreshness from './operations/backup_freshness'
import MonitoringStack from './operations/monitoring_stack'
import SmtpService from './operations/smtp_service'

// ConfigMap Validation (7)
import BrigConfigmap from './configmap_validation/brig'
import GalleyConfigmap from './configmap_validation/galley'
import GundeckConfigmap from './configmap_validation/gundeck'
import CannonConfigmap from './configmap_validation/cannon'
import CargoholdConfigmap from './configmap_validation/cargohold'
import SparConfigmap from './configmap_validation/spar'
import BackgroundWorkerConfigmap from './configmap_validation/background_worker'
// import SmallstepConfigmap from './configmap_validation/smallstep'  // disabled

/** All checkers, ordered by category. */
const all_checkers: BaseChecker[] = [
    // Host / Admin machine (7)
    new HostDiskUsage(),
    new HostMemoryUsage(),
    new HostCpuCount(),
    new HostLoadAverage(),
    new HostUptime(),
    new HostNtpSynchronized(),
    new HostNtpOffset(),

    // OS / System (3)
    new OsVersionMatches(),
    new KubenodeNtp(),
    new UnprivilegedPortStart(),

    // VMs (3)
    new VmDiskUsage(),
    new VmMemoryUsage(),
    new VmLoadAverage(),

    // DNS (2)
    new DnsSubdomainResolution(),
    new EmailDnsRecords(),

    // TLS / Certificates (4)
    new TlsCertificateExpiration(),
    new TlsChainValidity(),
    new KubeadmCertExpiration(),
    new OpensearchCertKeyUsage(),

    // Kubernetes (35)
    new K8sNodeCount(),
    new AllNodesReady(),
    new K8sVersion(),
    new ContainerRuntime(),
    new UnhealthyPods(),
    new TotalRunningPods(),
    new CertificatesReady(),
    new CertificateCount(),
    new IngressResources(),
    new MetricsApi(),
    new RestartCounts(),
    new PvcStatus(),
    new HelmChartVersions(),
    new EtcdHealth(),
    new SftNodeLabels(),
    new CoturnMemoryLimits(),
    new ConfigmapStaleness(),
    new CoreDnsHealth(),
    new CronJobHealth(),
    new DisruptionBudgets(),
    new HpaConfiguration(),
    new ImageConsistency(),
    new ImagePullPolicy(),
    new IngressTls(),
    new NodePressure(),
    new PodAntiAffinity(),
    new ProbeConfiguration(),
    new ReplicaCount(),
    new ResourceLimits(),
    new ResourceQuotas(),
    new SchedulingFailures(),
    new SecurityContext(),
    new ServiceEndpoints(),
    new StuckRollouts(),
    new WarningEvents(),

    // Data / Cassandra (7)
    new CassandraClusterStatus(),
    new CassandraNodeCount(),
    new CassandraNtpSynchronized(),
    new CassandraDataDiskUsage(),
    new CassandraKeyspaces(),
    new CassandraSparTables(),
    new CassandraSparIdpCount(),

    // Data / Elasticsearch (4)
    new EsClusterHealth(),
    new EsNodeCount(),
    new EsShardCount(),
    new EsReadOnlyMode(),

    // Data / PostgreSQL (4)
    new PgReplicationStatus(),
    new PgNodeCount(),
    new PgVersion(),
    new PgReplicationLag(),

    // Data / MinIO (5)
    new MinioNetworkStatus(),
    new MinioDrivesStatus(),
    new MinioBucketCount(),
    new MinioVersion(),
    new MinioErasureHealth(),

    // Data / RabbitMQ (6)
    new RmqClusterStatus(),
    new RmqNodeCount(),
    new RmqVersion(),
    new RmqQueueDepth(),
    new RmqAlarms(),
    new RmqQueuePersistence(),

    // Data / Redis (3)
    new RedisPodStatus(),
    new RedisMemoryEviction(),
    new RedisMaxmemoryConfigured(),

    // Wire Services (18)
    new BrigHealth(),
    new GalleyHealth(),
    new CannonHealth(),
    new CargoholdHealth(),
    new GundeckHealth(),
    new SparHealth(),
    new NginzHealth(),
    new BackgroundWorkerHealth(),
    new SftdHealth(),
    new CoturnHealth(),
    new WebappHealth(),
    new TeamSettingsHealth(),
    new AccountPagesHealth(),
    new HelmReleases(),
    new StatusEndpoints(),
    new WebappHttp(),
    new IngressResponse(),
    new AssetHost(),

    // Networking / Calling (3)
    new PortReachability(),
    new TurnConnectivity(),
    new SftdReachable(),

    // Networking / Ports (1)
    new PortConnectivity(),

    // Federation / MLS (2)
    new FederationDomainConsistency(),
    new BrigFederationDomain(),

    // MLS / Protocol (1)
    new MlsReadiness(),

    // Helm / Config Validation (10)
    new CassandraReplication(),
    new GalleyFeatureFlags(),
    new WebappBackendUrls(),
    new IsSelfHosted(),
    new DeeplinkJson(),
    new DatabaseHostConsistency(),
    new ServiceLogLevels(),
    new BrigSmsPlaceholder(),
    new BrigSmtpSecurity(),
    new IngressProxyProtocol(),

    // Site-survey: auto-detected settings
    new PushNotificationMode(),
    new RegistrationReport(),
    new SsoStatusReport(),
    new BrigEmailServiceMatch(),
    new FederationEnablement(),

    // Site-survey: user-declared settings
    new CallingConfiguration(),
    new TurnUrisValid(),
    new LegalholdConfiguration(),

    // Site-survey: federation
    new FederationStrategy(),
    new FederationRabbitmq(),
    new FederationCallingBrig(),
    new FederationCallingSft(),
    new FederationCallingCoturn(),
    new FederationTlsCerts(),
    new FederationSrvRecords(),
    new FederatorChecker(),

    // Site-survey: networking and infrastructure
    new InternetConnectivity(),
    new AwsSnsReachable(),
    new AwsSqsReachable(),
    new WireDeployDirectory(),
    new ImagePullIssues(),
    new NodeImageConsistency(),
    new LdapScimBridge(),

    // Client-mode checkers (analyzed per client result file)
    new ClientDnsResolution(),
    new ClientTlsValidity(),
    new ClientWebappReachable(),
    new ClientApiReachable(),
    new ClientWebsocketReachable(),
    new ClientCallingReachable(),
    new ClientDeeplinkJson(),
    new ClientFederationReachable(),

    // Secrets / Credentials (1)
    new SecretsRequiredPresent(),

    // Upgrades / Migrations (5)
    new MigrationJobs(),
    new HelmReleaseStatus(),
    new CertmanagerTestMode(),
    new VersionCurrency(),
    new EphemeralInProduction(),

    // Security / Hardening (3)
    new SternNotExposed(),
    new InternalEndpoints(),
    new RabbitmqDefaultCredentials(),

    // Operations / Tooling (4)
    new LogRotation(),
    new BackupFreshness(),
    new MonitoringStack(),
    new SmtpService(),

    // ConfigMap Validation (7)
    new BrigConfigmap(),
    new GalleyConfigmap(),
    new GundeckConfigmap(),
    new CannonConfigmap(),
    new CargoholdConfigmap(),
    new SparConfigmap(),
    new BackgroundWorkerConfigmap(),
    // new SmallstepConfigmap(),  // disabled — not shown in report
]

/**
 * Safe wrapper around render_template that returns the raw template string
 * if Handlebars compilation or rendering throws (e.g., malformed syntax).
 * Prevents a single bad template from crashing the entire report pipeline.
 */
function safe_render_template(template: string, context: Record<string, unknown>): string {
    try {
        return render_template(template, context)
    } catch {
        return template
    }
}

/**
 * Run all foundation checks against collected data points.
 *
 * Each checker gets a DataLookup instance that provides both the collected
 * data points and the gathering config (when available). Checkers can access
 * deployment-specific values like the cluster domain or database IPs via
 * data.config instead of hardcoding or guessing.
 *
 * Explanation always comes from the checker itself (checker.explanation).
 * Collection context (commands, timestamps) comes from the primary DataPoint
 * — the one most relevant to this checker, found via data_path or as the
 * last accessed point (checkers typically access helper data first, then
 * their primary data point last).
 */
export function run_checks(raw_data: DataPoint[], config: GatheringConfig | null = null): CheckOutput[] {
    const lookup: DataLookup = new DataLookup(raw_data, config)

    return all_checkers.map((checker: BaseChecker): CheckOutput => {
        try {
            // Reset access tracking so we only see DataPoints this checker touches
            lookup.reset_accessed()

        // In k8s-only mode, skip checkers that need SSH-based target data
        let result: ReturnType<BaseChecker['check']>
        if (config?.only_through_kubernetes && checker.requires_ssh) {
            result = { status: 'not_applicable' as const, status_reason: 'This check requires SSH access to collect data, which was not available in kubernetes-only mode.', recommendation: 'Skipped — data not collected in kubernetes-only mode.' }
        } else {
            // Per-checker error isolation: a single crashing checker must not lose all results
            try {
                result = checker.check(lookup)
            } catch (err: unknown) {
                const message = err instanceof Error ? err.message : String(err)
                result = { status: 'gather_failure' as const, status_reason: `Checker crashed: ${message}` }
            }
        }

        // Render Handlebars expressions in status_reason and fix_hint using template_data
        if (result.template_data) {
            result.status_reason = render_template(result.status_reason, result.template_data)
            if (result.fix_hint) {
                result.fix_hint = render_template(result.fix_hint, result.template_data)
            }
        }

            const accessed: DataPoint[] = lookup.accessed

            // Find the primary DataPoint for collection context (commands, timestamps).
            // If the checker declares data_path, look for an exact match in accessed.
            // Otherwise take the last accessed DataPoint — checkers typically access
            // helper/setup data first (e.g. helm versions), then their main data last.
            const primary_path = checker.data_path
            const primary_dp: DataPoint | undefined =
                (primary_path ? accessed.find((dp: DataPoint) => dp.path === primary_path) : undefined) ??
                accessed[accessed.length - 1]
            const primary_meta = primary_dp?.metadata

            // Deduplicate accessed DataPoints (a checker may access the same point
            // via get_applicable then get on the same path)
            const seen_paths = new Set<string>()
            const unique_accessed: DataPoint[] = []
            for (const dp of accessed) {
                if (!seen_paths.has(dp.path)) {
                    seen_paths.add(dp.path)
                    unique_accessed.push(dp)
                }
            }

            // Render Handlebars templates in explanation, status_reason, and fix_hint.
            // The template_data from the result provides variables for substitution.
            const tpl_ctx = result.template_data ?? {}

            return {
                path:     checker.path,
                name:     checker.name,
                category: checker.category,
                interest: checker.interest,
                ...result,
                // Render all text fields through Handlebars, falling back to raw template on error
                explanation:   safe_render_template(checker.explanation, tpl_ctx),
                status_reason: safe_render_template(result.status_reason, tpl_ctx),
                fix_hint:      result.fix_hint ? safe_render_template(result.fix_hint, tpl_ctx) : undefined,
                // Collection context from the primary DataPoint
                commands:         primary_meta?.commands,
                collected_at:     primary_meta?.collected_at,
                duration_seconds: primary_meta?.duration_seconds,
                gathered_from:    primary_meta?.gathered_from,
                // DataPoints the checker accessed, for the "Data points used" section
                data_points_used: unique_accessed.length > 0 ? unique_accessed : undefined,
            }
        } catch (err: unknown) {
            // Isolate failures: a single broken checker must not take down the report.
            // Return a gather_failure result so the UI shows an error for this one check.
            const message = err instanceof Error ? err.message : String(err)

            return {
                path:          checker.path,
                name:          checker.name,
                category:      checker.category,
                interest:      checker.interest,
                status:        'gather_failure',
                status_reason: `Checker crashed: ${message}`,
                explanation:   checker.explanation,
            }
        }
    })
}
