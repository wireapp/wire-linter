"""Loads and validates the Wire Fact Gathering Tool configuration file.

Checks required fields, validates formats (IPs, paths), provides typed access.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from src.lib.yaml_parser import parse_yaml, get_nested


class ConfigError(Exception):
    """Raised when config loading or validation fails.

    Collects all validation errors into one exception so the operator sees
    every problem at once (instead of fixing them one by one).

    Attributes:
        errors: List of individual error message strings.
    """

    def __init__(self, errors: list[str]) -> None:
        """Initialize with a list of error messages.

        Args:
            errors: All validation error messages collected during loading.
        """
        self.errors: list[str] = errors
        # format a human-readable message listing all errors
        super().__init__(
            f"Config validation failed with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


@dataclass
class AdminHostConfig:
    """Connection details for the admin/deploy host."""

    ip: str
    user: str
    ssh_key: str
    ssh_port: int


@dataclass
class ClusterConfig:
    """Wire cluster settings."""

    domain: str
    kubernetes_namespace: str


@dataclass
class KubernetesConfig:
    """Kubernetes access configuration.

    Wire offline deployments run kubectl inside a Docker container (wire-server-deploy image)
    on the admin host. When docker_image is set, every kubectl invocation gets wrapped
    in a «docker run» command via SSH on the admin host.

    When docker_image is «auto», we detect the image at startup by SSHing to the admin
    host and listing Docker images.
    """

    # docker image for running kubectl (empty = kubectl runs directly).
    # set to «auto» to auto-detect the wire-server-deploy image on the admin host.
    docker_image: str
    # home directory of SSH user on admin host (needed for Docker volume mounts).
    # defaults to /home/<admin_host.user>.
    admin_home: str
    # whether kubectl should route through the admin host via SSH.
    # decoupled from databases.ssh_key which controls the inner hop to DB VMs.
    # when not set in the config file, defaults to bool(databases.ssh_key) for
    # backward compatibility.
    route_via_ssh: bool


@dataclass
class DatabasesConfig:
    """Database host addresses and optional SSH settings for reaching them.

    When database hosts are on a private network behind the admin host, the runner
    uses the admin host as an SSH jump host. The ssh_user, ssh_key, ssh_port fields
    configure the inner hop (admin → database).
    """

    cassandra: str
    elasticsearch: str
    minio: str
    postgresql: str
    # rabbitmq defaults to cassandra if not set (in standard Wire, they're co-located
    # on the same datanodes). set explicitly if rabbitmq runs on dedicated broker VMs.
    rabbitmq: str
    # ssh credentials for inner hop when jumping through admin host.
    # ssh_key is a path ON the admin/jump host (not the local machine).
    ssh_user: str   # defaults to admin_host.user
    ssh_key: str    # defaults to admin_host.ssh_key (empty = no jump needed)
    ssh_port: int   # defaults to 22
    # cassandra auth creds. Wire ships with cassandra/cassandra (default account).
    # set these when your deployment uses custom creds.
    cassandra_username: str = 'cassandra'
    cassandra_password: str = 'cassandra'
    # elasticsearch auth creds. ES 8.x enables X-Pack security by default,
    # requiring basic auth. Empty strings mean no authentication (pre-8.x clusters).
    elasticsearch_username: str = ''
    elasticsearch_password: str = ''


@dataclass
class OptionsConfig:
    """Fact gathering options and deployment feature flags.

    The check_* flags control which target groups to collect. The expect_*
    flags tell the UI checkers what to expect from this deployment so they
    can skip warnings for features that aren't in use.
    """

    check_kubernetes: bool
    check_databases: bool
    check_network: bool
    check_wire_services: bool
    output_format: str
    output_file: str
    # Deployment feature flags all default false except where noted.
    # Checkers skip warnings for features the operator says aren't deployed.
    expect_metrics: bool = False
    expect_sso: bool = False
    expect_deeplink: bool = False
    expect_sms: bool = False
    expect_sft: bool = False
    using_ephemeral_databases: bool = False
    # Site-survey-derived flags (user-declared in Step 2)
    wire_managed_cluster: bool = True
    has_internet: bool = True
    has_dns: bool = True
    users_access_externally: bool = True
    expect_calling: bool = True
    # "on_prem" or "cloud"
    calling_type: str = 'on_prem'
    calling_in_dmz: bool = False
    expect_federation: bool = False
    # Domain names of federation partners
    federation_domains: list[str] | None = None
    expect_legalhold: bool = False


@dataclass
class NodesConfig:
    """Explicit VM node IP lists.

    When non-empty, these override dynamic host discovery:
    kube_nodes: used instead of running kubectl get nodes
    data_nodes: used instead of deriving hosts from databases.* IPs

    Both lists contain plain IPv4 addresses. Nodes are named kubenode-{ip}
    and datanode-{ip} respectively so all results use a consistent format.
    When a list is empty the runner falls back to the original discovery.
    """

    # IP addresses of Kubernetes cluster nodes
    kube_nodes: list[str]
    # IP addresses of data/database VMs (cassandra, elasticsearch, minio, etc.)
    data_nodes: list[str]
    # IP of the asset host VM (serves static files for the webapp). Empty means
    # fall back to localhost on the admin host. In offline deployments the asset
    # host is typically a separate VM.
    assethost: str = ''


@dataclass
class Config:
    """Complete runner configuration."""

    admin_host: AdminHostConfig
    cluster: ClusterConfig
    databases: DatabasesConfig
    kubernetes: KubernetesConfig
    options: OptionsConfig
    # Explicit node lists when non-empty override dynamic host discovery
    nodes: NodesConfig
    # Empty string means use current kubectl context
    kubernetes_context: str
    # Defaults to cluster.domain if not explicitly set
    wire_domain: str
    # Command execution timeout in seconds, defaults to 30
    timeout: int
    # Entire parsed YAML dict for targets that need custom fields
    raw: dict[str, Any]
    # Where the gatherer is running: 'admin-host' (directly on the Wire deploy host),
    # 'ssh-into-admin-host' (SSH from a remote machine into admin host), or 'client'
    # (client-side probe — no SSH/kubectl, tests external reachability only).
    # Passed via CLI --source, not stored in the config file.
    gathered_from: str = 'ssh-into-admin-host'
    # When True, only kubectl-based targets run. SSH-dependent targets are skipped
    # with a not_applicable sentinel. Set via CLI --only-through-kubernetes flag.
    only_through_kubernetes: bool = False
    # Human-readable label for this runner invocation (e.g. "main-cluster",
    # "calling-dmz", "office-lan"). Set via CLI --network-name.
    network_name: str = ''
    # Derived from gathered_from: "backend" for admin-host/ssh-into-admin-host,
    # "client" for client mode.
    source_type: str = 'backend'
    # Which cluster this run targets: "both" (default), "main", or "calling".
    # Set via CLI --cluster-type. Targets with non-matching affinity are skipped.
    cluster_type: str = 'both'
    # When True, no commands are executed. Instead, each execution method records
    # what it would have done, and the runner prints a summary table at the end.
    # Set via CLI --dry-run.
    dry_run: bool = False


def is_valid_ipv4(ip: str) -> bool:
    """Check if a string is a valid IPv4 address.

    Validates that it's exactly 4 dot-separated decimal octets, each 0-255,
    no leading zeros on multi-digit octets.

    Args:
        ip: The string to validate.

    Returns:
        True if valid IPv4, False otherwise.
    """
    # split into octets, must be exactly 4
    parts: list[str] = ip.split('.')
    if len(parts) != 4:
        return False

    for part in parts:
        # each part must be non-empty and all digits
        if not part or not part.isdigit():
            return False

        # check range
        value: int = int(part)
        if value < 0 or value > 255:
            return False

        # no leading zeros on multi-digit octets («01» is invalid)
        if len(part) > 1 and part[0] == '0':
            return False

    return True


# rfc 1123 hostname pattern: alphanumeric labels separated by dots, hyphens
# allowed mid-label, each label 1-63 chars, total up to 253 chars.
_HOSTNAME_RE: re.Pattern[str] = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
)

# safe filesystem path: only alphanumeric, forward slashes, hyphens,
# underscores, and dots. rejects spaces and shell metacharacters ($, `, ;,
# |, &, etc.) that would break unquoted interpolation into shell commands.
_SAFE_PATH_RE: re.Pattern[str] = re.compile(r'^[a-zA-Z0-9/_.\-]+$')

# safe docker image reference: same as path plus colon (tags) and @ (digests).
_SAFE_DOCKER_IMAGE_RE: re.Pattern[str] = re.compile(r'^[a-zA-Z0-9/_.\-:@]+$')


def _get_bool(
    data: dict[str, Any], path: str, default: bool, errors: list[str]
) -> bool:
    """Read a boolean value from nested config data, validating its type.

    The YAML parser converts true/false/yes/no to Python bool, but other
    values (integers, arbitrary strings) pass through as their parsed type.
    This helper rejects non-boolean values so config typos don't silently
    enable or disable features.

    Args:
        data: The parsed YAML config dict.
        path: Dot-separated path to the value (e.g. 'options.check_kubernetes').
        default: Value to use when the key is absent from the config.
        errors: Validation error list to append to when the value is wrong type.

    Returns:
        The boolean value if valid, or the default if missing or wrong type.
    """
    value: Any = get_nested(data, path, default)
    # missing keys return the default (already a bool), no validation needed
    if not isinstance(value, bool):
        errors.append(f"{path} must be a boolean (true/false), got: {value!r}")
        return default
    return value


def is_valid_host(host: str) -> bool:
    """Check if a string is a valid IPv4 address or hostname.

    Accepts either a dotted-quad IPv4 or an RFC 1123 hostname. SSH works
    with both, so the runner accepts either format.

    Args:
        host: The string to validate.

    Returns:
        True if valid IPv4 or hostname, False otherwise.
    """
    if is_valid_ipv4(host):
        return True

    # reject empty, whitespace, or overly long strings
    if not host or ' ' in host or len(host) > 253:
        return False

    return bool(_HOSTNAME_RE.match(host))


def load_config(file_path: str, gathered_from: str = 'ssh-into-admin-host') -> Config:
    """Load and validate a config file.

    Reads the YAML file, validates all required fields, checks IP formats,
    verifies SSH key file exists, returns a typed Config object.

    All validation errors collected and raised together so you see every
    problem at once.

    Args:
        file_path: Path to the YAML config file.
        gathered_from: Where the tool runs from ('admin-host', 'ssh-into-admin-host', or 'client').
            When 'admin-host', SSH key file existence is not checked since
            the tool runs locally and does not SSH into the admin host.

    Returns:
        A validated Config object.

    Raises:
        ConfigError: If file can't be read, parsed, or validation fails
            (includes ALL validation failures).
    """
    # read the config file (fatal errors raised immediately)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text: str = f.read()
    except FileNotFoundError:
        raise ConfigError([f"Config file not found: {file_path}"])
    except OSError as e:
        raise ConfigError([f"Cannot read config file: {file_path}: {e}"])

    # parse yaml (fatal immediately)
    try:
        data: dict[str, Any] = parse_yaml(text)
    except ValueError as e:
        raise ConfigError([f"YAML parse error: {e}"])

    # collect all validation errors before raising
    errors: list[str] = []

    # client mode relaxes validation — only cluster.domain and options are required,
    # everything about admin host, SSH, databases, and kubernetes is optional
    is_client_mode: bool = gathered_from == 'client'

    # admin_host section (optional in client mode)

    # admin_host.ip (required in backend mode, optional in client mode)
    admin_ip: str | None = get_nested(data, 'admin_host.ip')
    if not admin_ip and not is_client_mode:
        errors.append("Missing required field: admin_host.ip")
    elif admin_ip and not is_valid_host(str(admin_ip)):
        errors.append(f"Invalid host for admin_host.ip: {admin_ip}")

    # admin_host.user (required in backend mode, optional in client mode)
    admin_user: str | None = get_nested(data, 'admin_host.user')
    if not admin_user and not is_client_mode:
        errors.append("Missing required field: admin_host.user")

    # admin_host.ssh_key (required in backend mode, optional in client mode)
    # When running from the admin host itself, the file need not exist locally
    # because we won't SSH into the admin host — but the value is still needed
    # for database SSH connections that reference the key path.
    admin_ssh_key: str | None = get_nested(data, 'admin_host.ssh_key')
    expanded_ssh_key: str = ''
    if not admin_ssh_key and not is_client_mode:
        errors.append("Missing required field: admin_host.ssh_key")
    elif admin_ssh_key:
        expanded_ssh_key = os.path.expanduser(str(admin_ssh_key))
        # only check file existence when SSHing into the admin host from outside
        if gathered_from == 'ssh-into-admin-host' and not os.path.exists(expanded_ssh_key):
            errors.append(f"SSH key file not found: {expanded_ssh_key}")

    # admin_host.ssh_port (required in backend mode, defaults to 22 in client mode)
    admin_ssh_port: Any = get_nested(data, 'admin_host.ssh_port')
    if admin_ssh_port is None and not is_client_mode:
        errors.append("Missing required field: admin_host.ssh_port")
    elif admin_ssh_port is None:
        # client mode: default to 22
        admin_ssh_port = 22
    elif not isinstance(admin_ssh_port, int):
        errors.append(f"admin_host.ssh_port must be an integer, got: {admin_ssh_port}")
    elif admin_ssh_port < 1 or admin_ssh_port > 65535:
        errors.append(f"admin_host.ssh_port must be 1-65535, got: {admin_ssh_port}")

    # cluster section

    # cluster.domain (required, must be a valid hostname — shell-interpolated by targets)
    cluster_domain: str | None = get_nested(data, 'cluster.domain')
    if not cluster_domain:
        errors.append("Missing required field: cluster.domain")
    elif len(str(cluster_domain)) > 253 or not _HOSTNAME_RE.match(str(cluster_domain)):
        errors.append(f"Invalid domain for cluster.domain: {cluster_domain}")

    # cluster.kubernetes_namespace (required in backend mode, defaults to 'wire' in client mode)
    cluster_namespace: str | None = get_nested(data, 'cluster.kubernetes_namespace')
    if not cluster_namespace and not is_client_mode:
        errors.append("Missing required field: cluster.kubernetes_namespace")
    elif not cluster_namespace:
        # client mode: default to 'wire'
        cluster_namespace = 'wire'

    # databases section (all optional in client mode)

    # each db field must be a valid ipv4 or hostname
    db_names: list[str] = ['cassandra', 'elasticsearch', 'minio', 'postgresql']
    db_ips: dict[str, str] = {}
    for db_name in db_names:
        db_value: str | None = get_nested(data, f'databases.{db_name}')
        if not db_value and not is_client_mode:
            errors.append(f"Missing required field: databases.{db_name}")
        elif db_value and not is_valid_host(str(db_value)):
            errors.append(f"Invalid host for databases.{db_name}: {db_value}")
        elif db_value:
            db_ips[db_name] = str(db_value)

    # rabbitmq is optional (falls back to cassandra when not specified,
    # since in standard Wire they're co-located on datanodes).
    raw_rabbitmq: str | None = get_nested(data, 'databases.rabbitmq')
    if raw_rabbitmq:
        if not is_valid_host(str(raw_rabbitmq)):
            errors.append(f"Invalid host for databases.rabbitmq: {raw_rabbitmq}")
        else:
            db_ips['rabbitmq'] = str(raw_rabbitmq)
    elif 'cassandra' in db_ips:
        # co-location fallback: use cassandra when rabbitmq not set
        db_ips['rabbitmq'] = db_ips['cassandra']

    # nodes section (optional, defaults to empty lists)

    # kube_nodes: list of kubenode IPs (overrides kubectl discovery when non-empty)
    raw_kube_nodes: list[Any] = get_nested(data, 'nodes.kube_nodes', []) or []
    if not isinstance(raw_kube_nodes, list):
        errors.append('nodes.kube_nodes must be a list of IP addresses, got a single value')
        raw_kube_nodes = []
    kube_nodes: list[str] = [str(ip) for ip in raw_kube_nodes if ip]
    for kube_ip in kube_nodes:
        if not is_valid_host(kube_ip):
            errors.append(f"Invalid host in nodes.kube_nodes: {kube_ip}")

    # data_nodes: list of datanode IPs (overrides config.databases.* when non-empty)
    raw_data_nodes: list[Any] = get_nested(data, 'nodes.data_nodes', []) or []
    if not isinstance(raw_data_nodes, list):
        errors.append('nodes.data_nodes must be a list of IP addresses, got a single value')
        raw_data_nodes = []
    data_nodes: list[str] = [str(ip) for ip in raw_data_nodes if ip]
    for data_ip in data_nodes:
        if not is_valid_host(data_ip):
            errors.append(f"Invalid host in nodes.data_nodes: {data_ip}")

    # assethost: IP of the asset host VM (optional, empty = localhost on admin host)
    assethost: str = str(get_nested(data, 'nodes.assethost', '') or '')
    if assethost and not is_valid_host(assethost):
        errors.append(f"Invalid host for nodes.assethost: {assethost}")

    # options section (all optional with defaults)

    check_kubernetes: bool = _get_bool(data, 'options.check_kubernetes', True, errors)
    check_databases: bool = _get_bool(data, 'options.check_databases', True, errors)
    check_network: bool = _get_bool(data, 'options.check_network', True, errors)
    check_wire_services: bool = _get_bool(data, 'options.check_wire_services', True, errors)
    output_format: str = get_nested(data, 'options.output_format', 'jsonl')
    if output_format not in ('jsonl',):
        errors.append(f"options.output_format must be 'jsonl', got: {output_format!r}")
    output_file: str = get_nested(data, 'options.output_file', 'results.jsonl')

    # Deployment feature flags tell checkers what to expect
    expect_metrics: bool = _get_bool(data, 'options.expect_metrics', False, errors)
    expect_sso: bool = _get_bool(data, 'options.expect_sso', False, errors)
    expect_deeplink: bool = _get_bool(data, 'options.expect_deeplink', False, errors)
    expect_sms: bool = _get_bool(data, 'options.expect_sms', False, errors)
    expect_sft: bool = _get_bool(data, 'options.expect_sft', False, errors)
    using_ephemeral_databases: bool = _get_bool(data, 'options.using_ephemeral_databases', False, errors)

    # Site-survey-derived flags (user-declared in Step 2 configuration form)
    wire_managed_cluster: bool = _get_bool(data, 'options.wire_managed_cluster', True, errors)
    has_internet: bool = _get_bool(data, 'options.has_internet', True, errors)
    has_dns: bool = _get_bool(data, 'options.has_dns', True, errors)
    users_access_externally: bool = _get_bool(data, 'options.users_access_externally', True, errors)
    expect_calling: bool = _get_bool(data, 'options.expect_calling', True, errors)
    calling_in_dmz: bool = _get_bool(data, 'options.calling_in_dmz', False, errors)
    expect_federation: bool = _get_bool(data, 'options.expect_federation', False, errors)
    expect_legalhold: bool = _get_bool(data, 'options.expect_legalhold', False, errors)

    # calling_type: "on_prem" or "cloud", defaults to "on_prem"
    calling_type: str = str(get_nested(data, 'options.calling_type', 'on_prem') or 'on_prem')
    if calling_type not in ('on_prem', 'cloud'):
        errors.append(f"options.calling_type must be 'on_prem' or 'cloud', got: {calling_type!r}")
        calling_type = 'on_prem'

    # federation_domains: list of partner domain names
    raw_federation_domains: list[Any] = get_nested(data, 'options.federation_domains', []) or []
    if not isinstance(raw_federation_domains, list):
        errors.append('options.federation_domains must be a list of domain names')
        raw_federation_domains = []
    federation_domains: list[str] = [str(d).strip() for d in raw_federation_domains if d]
    for fed_domain in federation_domains:
        if len(fed_domain) > 253 or not _HOSTNAME_RE.match(fed_domain):
            errors.append(f"Invalid domain in options.federation_domains: {fed_domain}")

    # kubernetes section

    # docker image for running kubectl in Wire offline deployments.
    # «auto» means detect at startup, empty means run kubectl directly.
    # explicit None check so that docker_image: "" means «run kubectl directly».
    _raw_docker_image = get_nested(data, 'kubernetes.docker_image', None)
    kubectl_docker_image: str = 'auto' if _raw_docker_image is None else str(_raw_docker_image)

    # home directory on admin host (for Docker volume mounts).
    # raw value read here; fallback to /home/{admin_user} is deferred
    # until after validation, where admin_user is guaranteed non-None.
    raw_admin_home: str = str(get_nested(data, 'kubernetes.admin_home', '') or '')

    # kubernetes.route_via_ssh controls whether kubectl routes through admin host SSH.
    # when not set, falls back to bool(databases.ssh_key) for backward compatibility.
    _raw_route_via_ssh = get_nested(data, 'kubernetes.route_via_ssh', None)
    db_ssh_key_str: str = str(get_nested(data, 'databases.ssh_key', '') or '')
    if _raw_route_via_ssh is not None and not isinstance(_raw_route_via_ssh, bool):
        errors.append(
            f"kubernetes.route_via_ssh must be a boolean (true/false), got: {_raw_route_via_ssh!r}"
        )
    kubectl_route_via_ssh: bool = (
        bool(_raw_route_via_ssh)
        if _raw_route_via_ssh is not None
        else bool(db_ssh_key_str)
    )

    # shell-safety checks for values interpolated into shell commands.
    # admin_home and docker_image are used in Docker «-v» and image arguments
    # built via f-strings (helm targets, kubectl wrappers). reject any
    # characters that could break unquoted shell interpolation.

    # admin_host.user feeds the default admin_home (/home/{user}), so it
    # must also be free of spaces and shell metacharacters
    if admin_user and not _SAFE_PATH_RE.match(str(admin_user)):
        errors.append(
            f"admin_host.user contains shell-unsafe characters: {admin_user!r} "
            "(only alphanumeric, hyphens, underscores, dots allowed)"
        )

    # kubernetes.admin_home is interpolated into Docker volume mount flags
    if raw_admin_home and not _SAFE_PATH_RE.match(raw_admin_home):
        errors.append(
            f"kubernetes.admin_home contains shell-unsafe characters: {raw_admin_home!r} "
            "(only alphanumeric, slashes, hyphens, underscores, dots allowed)"
        )

    # docker_image is interpolated into shell commands when explicitly set
    if (kubectl_docker_image
            and kubectl_docker_image != 'auto'
            and not _SAFE_DOCKER_IMAGE_RE.match(kubectl_docker_image)):
        errors.append(
            f"kubernetes.docker_image contains shell-unsafe characters: {kubectl_docker_image!r} "
            "(must be a valid Docker image reference)"
        )

    # databases.ssh_port (optional, defaults to 22, must be integer 1-65535)
    db_ssh_port_raw: Any = get_nested(data, 'databases.ssh_port', 22)
    db_ssh_port: int = 22
    if not isinstance(db_ssh_port_raw, int):
        errors.append(f"databases.ssh_port must be an integer, got: {db_ssh_port_raw}")
    elif db_ssh_port_raw < 1 or db_ssh_port_raw > 65535:
        errors.append(f"databases.ssh_port must be 1-65535, got: {db_ssh_port_raw}")
    else:
        db_ssh_port = db_ssh_port_raw

    # elasticsearch credentials must be provided as a pair: if username is set,
    # password must also be set. A username without a password would send empty-
    # password auth to ES, which can trigger account lockouts or misleading errors.
    es_username_raw: str = str(get_nested(data, 'databases.elasticsearch_username', '') or '')
    es_password_raw: str = str(get_nested(data, 'databases.elasticsearch_password', '') or '')
    if es_username_raw and not es_password_raw:
        errors.append(
            "databases.elasticsearch_username is set but databases.elasticsearch_password is empty — "
            "both must be provided together, or both left empty for unauthenticated access"
        )
    if es_password_raw and not es_username_raw:
        errors.append(
            "databases.elasticsearch_password is set but databases.elasticsearch_username is empty — "
            "both must be provided together, or both left empty for unauthenticated access"
        )

    # convenience fields with defaults

    # empty string means use current kubectl context
    kubernetes_context: str = get_nested(data, 'kubernetes_context', '')

    # falls back to cluster.domain if not explicitly set
    wire_domain: str = get_nested(data, 'wire_domain', None) or (cluster_domain or '')

    # default 30 seconds for command execution timeouts
    timeout_raw: Any = get_nested(data, 'timeout', 30)
    timeout: int = 30
    if isinstance(timeout_raw, bool) or not isinstance(timeout_raw, int):
        errors.append(f"timeout must be an integer, got: {timeout_raw}")
    elif timeout_raw < 1:
        errors.append(f"timeout must be >= 1, got: {timeout_raw}")
    else:
        timeout = timeout_raw

    # raise collected errors if any

    if len(errors) > 0:
        raise ConfigError(errors)

    # admin_user is guaranteed non-None after validation (except in client mode
    # where it defaults to empty string)
    admin_home: str = raw_admin_home or f'/home/{admin_user or "wire"}'

    # build and return the Config dataclass

    return Config(
        admin_host=AdminHostConfig(
            ip=str(admin_ip or ''),
            user=str(admin_user or ''),
            ssh_key=expanded_ssh_key,
            ssh_port=admin_ssh_port,
        ),
        cluster=ClusterConfig(
            domain=str(cluster_domain),
            kubernetes_namespace=str(cluster_namespace),
        ),
        databases=DatabasesConfig(
            # in client mode, db fields may be empty — use .get() with empty-string fallback
            cassandra=db_ips.get('cassandra', ''),
            elasticsearch=db_ips.get('elasticsearch', ''),
            minio=db_ips.get('minio', ''),
            postgresql=db_ips.get('postgresql', ''),
            # falls back to cassandra when not explicitly set (co-located deployment)
            rabbitmq=db_ips.get('rabbitmq', db_ips.get('cassandra', '')),
            # inner-hop ssh creds for jumping through admin host to reach DB VMs.
            # empty ssh_key means direct SSH (no jump needed).
            ssh_user=str(get_nested(data, 'databases.ssh_user', '') or admin_user or ''),
            ssh_key=str(get_nested(data, 'databases.ssh_key', '') or ''),
            ssh_port=db_ssh_port,
            # cassandra auth creds (default to Wire/Cassandra standard account).
            cassandra_username=str(get_nested(data, 'databases.cassandra_username', 'cassandra')),
            cassandra_password=str(get_nested(data, 'databases.cassandra_password', 'cassandra')),
            # elasticsearch auth creds (empty = no auth for pre-8.x clusters).
            elasticsearch_username=str(get_nested(data, 'databases.elasticsearch_username', '') or ''),
            elasticsearch_password=str(get_nested(data, 'databases.elasticsearch_password', '') or ''),
        ),
        kubernetes=KubernetesConfig(
            docker_image=kubectl_docker_image,
            admin_home=admin_home,
            route_via_ssh=kubectl_route_via_ssh,
        ),
        nodes=NodesConfig(
            kube_nodes=kube_nodes,
            data_nodes=data_nodes,
            assethost=assethost,
        ),
        options=OptionsConfig(
            check_kubernetes=check_kubernetes,
            check_databases=check_databases,
            check_network=check_network,
            check_wire_services=check_wire_services,
            output_format=output_format,
            output_file=output_file,
            expect_metrics=expect_metrics,
            expect_sso=expect_sso,
            expect_deeplink=expect_deeplink,
            expect_sms=expect_sms,
            expect_sft=expect_sft,
            using_ephemeral_databases=using_ephemeral_databases,
            wire_managed_cluster=wire_managed_cluster,
            has_internet=has_internet,
            has_dns=has_dns,
            users_access_externally=users_access_externally,
            expect_calling=expect_calling,
            calling_type=calling_type,
            calling_in_dmz=calling_in_dmz,
            expect_federation=expect_federation,
            federation_domains=federation_domains,
            expect_legalhold=expect_legalhold,
        ),
        kubernetes_context=kubernetes_context,
        wire_domain=wire_domain,
        timeout=timeout,
        raw=data,
    )
