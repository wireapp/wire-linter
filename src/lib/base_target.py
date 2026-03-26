"""Base class for all information gathering targets.

Every target inherits the shared interface here: error handling, output formatting,
command execution helpers, all the lifecycle stuff. New targets just implement collect().

Related modules:
    per_host_target.py: Extends BaseTarget for targets that iterate over multiple
      hosts (emit one data point per host).
    target_discovery.py: Scans src/targets/ to discover target classes automatically.
      No registry needed.

Exceptions:
    NotApplicableError: Targets raise this from collect() when they discover at
      runtime that they cannot gather data (e.g. no RabbitMQ pods in k8s when
      RabbitMQ runs on VMs). The execute() method catches it and emits a
      not_applicable sentinel instead of recording a collection failure.
"""

from __future__ import annotations

import datetime
import enum
import json
import shlex
import threading
import time
from dataclasses import dataclass
from typing import Any

from src.lib.command import CommandResult, run_command
from src.lib.config import Config
from src.lib.cql_client import CqlClient
from src.lib.cql_types import CqlResult, CqlConnectionError, CqlError
from src.lib.display_helpers import summarize_kubectl_item, format_cql_result
from src.lib.dry_run import CommandRecord
from src.lib.http_client import HttpResult, http_get, http_get_via_ssh
from src.lib.kubectl import kubectl_get, kubectl_raw, detect_kubectl_docker_image, detect_kubectl_docker_image_local, int_or_zero
from src.lib.logger import Logger
from src.lib.output import DataPoint
from src.lib.ssh import SSH, SSHTarget, SSHTunnel
from src.lib.terminal import Terminal
from src.lib.vm_hosts import discover_kube_node_ips


def now_utc_str() -> str:
    """Return the current UTC time as an ISO 8601 string.

    Single source of truth for the timestamp format used in all DataPoint
    metadata, so changing the format only requires editing this one place.

    Returns:
        UTC timestamp string like '2024-03-15T14:30:00Z'.
    """
    return datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


class NotApplicableError(Exception):
    """Raised by collect() when a target discovers at runtime it cannot gather data.

    Unlike the static requires_ssh / requires_external_access checks (which are
    evaluated before collect() runs), this covers situations where the target
    needs to attempt something first before it knows the data isn't available.

    Example: direct/rabbitmq targets try to find RabbitMQ pods via kubectl.
    In production Wire deployments RabbitMQ runs on VMs, not k8s, so no pods
    exist. Rather than reporting a collection failure, we emit a not_applicable
    sentinel so the UI can grey it out and the summary doesn't show a scary error.

    Args:
        reason: Human-readable explanation of why data isn't available.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason: str = reason


@dataclass
class TargetResult:
    """Result from a single target execution."""

    data_point: DataPoint | None  # None only if target failed before producing any data
    success: bool
    error: str | None  # Error message if failed, None on success
    duration_seconds: float


class SourceMode(enum.Enum):
    """Which source mode a target runs in.

    Controls whether a target is executed based on the --source CLI flag.
    BACKEND targets run when --source is admin-host or ssh-into-admin-host.
    CLIENT targets run when --source is client. BOTH targets run regardless
    of the source mode.
    """

    BACKEND = 'backend'
    CLIENT = 'client'
    BOTH = 'both'


class BaseTarget:
    """Base class for all information gathering targets.

    Subclasses just implement collect(). Error handling, output formatting,
    command helpers, logging... all provided. The target path comes from its
    location relative to src/targets/. So src/targets/databases/cassandra/cluster_status.py
    becomes 'databases/cassandra/cluster_status'.
    """

    # Class-level cache for the auto-detected kubectl Docker image.
    # Detected once on first kubectl call, then reused for all targets.
    _kubectl_docker_image: str | None = None

    # Lock guarding the auto-detection block so only one thread runs the SSH
    # detection call; all others wait and reuse the cached result.
    _kubectl_docker_image_lock: threading.Lock = threading.Lock()

    # Class-level cache for the ingress-nginx HTTPS NodePort. Discovered once
    # via kubectl on first HTTP check that needs it, then reused by all others.
    # None = not yet detected. 0 = detected but no NodePort found.
    _ingress_https_nodeport: int | None = None
    _ingress_nodeport_lock: threading.Lock = threading.Lock()

    # Class-level cache for the first kube node IP discovered via kubectl.
    # None = not yet attempted. '' = attempted but no nodes found.
    _discovered_kube_node_ip: str | None = None
    _kube_node_ip_lock: threading.Lock = threading.Lock()

    @classmethod
    def reset_caches(cls) -> None:
        """Reset all class-level caches to their initial state.

        Called by Runner.run() before target execution so that consecutive
        invocations in the same process (tests, REPL, library usage) do not
        leak cached values from a previous run's cluster.
        """
        cls._kubectl_docker_image = None
        cls._ingress_https_nodeport = None
        cls._discovered_kube_node_ip = None

    # Set to True in subclasses that can only be meaningfully tested from an
    # internet-connected machine. When gathered_from == 'admin-host', these
    # targets emit a not_applicable data point instead of running collect().
    requires_external_access: bool = False

    # Set to True in subclasses that need SSH access to VMs, database hosts,
    # or the admin host. When only_through_kubernetes is True, these targets
    # emit a not_applicable data point instead of running collect().
    requires_ssh: bool = False

    # Which source mode this target runs in. BACKEND (default) targets only run
    # with --source admin-host or ssh-into-admin-host. CLIENT targets only run
    # with --source client. BOTH targets run regardless of source mode.
    source_mode: SourceMode = SourceMode.BACKEND

    # Which cluster this target is relevant to: "both" (default), "main", or "calling".
    # Used with --cluster-type to filter targets. When the runner's cluster_type does
    # not match this target's affinity, the target is skipped.
    cluster_affinity: str = 'both'

    def __init__(self, config: Config, terminal: Terminal, logger: Logger) -> None:
        """Initialize the target with shared dependencies.

        Args:
            config: The validated runner configuration.
            terminal: Terminal output manager for progress display.
            logger: Logger instance.
        """
        self.config: Config = config
        self.terminal: Terminal = terminal
        self.logger: Logger = logger
        # Fluent SSH builder shared across all command helpers
        self.ssh: SSH = SSH(config)

        # Set by the target discovery system, not by the target itself
        self._path: str = ""

        # Allows collect() to override the static description at runtime
        self._dynamic_description: str | None = None

        # Populated by command helpers during collect()
        self._raw_outputs: list[str] = []

        # Tracks all commands executed during collect()
        self._commands_run: list[str] = []

        # --- Optional: secondary health assessment ---
        # Targets can set this in collect() to provide an informational
        # health interpretation of the collected data. This is SECONDARY
        # to the primary value it does not affect success/failure, which
        # is purely about whether data was collected. Displayed as a gray
        # info line in the terminal output.
        self._health_info: str | None = None

        # Dry-run command recording. Populated by execution methods when
        # config.dry_run is True. The runner collects these after execute().
        self._dry_run_records: list[CommandRecord] = []

    @property
    def path(self) -> str:
        """The target's hierarchical path (e.g., 'databases/cassandra/cluster_status')."""
        return self._path

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks.

        Must be overridden by subclasses.
        """
        raise NotImplementedError("Subclasses must define a description property")

    @property
    def explanation(self) -> str | None:
        """Why this check exists and what determines healthy vs unhealthy.

        Override in subclasses to provide meaningful context about what is
        being checked and why it matters. Returns None by default so callers
        can use a simple None check instead of try/except.
        """
        return None

    @property
    def unit(self) -> str:
        """Unit of measurement for the value (e.g., '%', 'nodes', 'Gi').

        Override in subclasses. Defaults to empty string.
        """
        return ""

    def collect(self) -> str | int | float | bool | None:
        """Collect the data point value.

        This is what subclasses implement. Run whatever commands/checks you need,
        parse the output, return the value. Use self.run_local(), self.run_ssh(),
        self.run_kubectl() etc. for command execution (they auto-track raw output).

        Error signaling contract:

            Return a value:     Collection succeeded. The UI checker analyzes the
                                value (e.g. integer for thresholds, string for
                                pattern matching). Use self._health_info for a
                                human-readable health assessment alongside the value.

            Return None:        Collection succeeded but there is no meaningful
                                value (e.g. the target produced structured metadata
                                only). The DataPoint is still emitted.

            Raise RuntimeError: Collection failed due to unexpected conditions
                                (unparseable output, missing data). The execute()
                                lifecycle catches it and records a failed DataPoint
                                with the error message. The UI shows a red error.

            Raise NotApplicableError:
                                Collection cannot proceed because this check does
                                not apply to the current environment (e.g. service
                                not deployed, VM-only feature on a k8s-only cluster).
                                The UI greys out the check rather than showing an
                                error. Use this instead of RuntimeError when the
                                absence is expected and not a problem.

        Returns:
            The collected value (any JSON-serializable primitive).

        Raises:
            NotApplicableError: When the check is inapplicable to this environment.
            RuntimeError: When collection fails unexpectedly.
            Any other exception: Treated the same as RuntimeError by execute().
        """
        raise NotImplementedError("Subclasses must implement collect()")

    def _reset_accumulators(self) -> None:
        """Clear per-collection accumulators so stale state from a prior run
        doesn't leak into the next target or per-item iteration.

        Called at the start of execute(), execute_all(), and before each item
        in iterable targets.
        """
        self._raw_outputs = []
        self._commands_run = []
        self._dynamic_description = None
        self._health_info = None

    def _build_base_metadata(self, start_time: float, **extra: Any) -> dict[str, Any]:
        """Build the standard metadata dict shared by all DataPoints.

        Centralizes the collected_at timestamp, commands list, duration, gathered_from,
        and optional explanation so every call site stays consistent.

        Args:
            start_time: Monotonic timestamp from before the collection started.
            **extra: Additional key-value pairs merged into the dict.

        Returns:
            Metadata dict ready for DataPoint construction.
        """
        duration_seconds: float = round(time.monotonic() - start_time, 3)

        metadata: dict[str, Any] = {
            "collected_at": now_utc_str(),
            "commands": self._commands_run.copy(),
            "duration_seconds": duration_seconds,
            "gathered_from": self.config.gathered_from,
        }

        # Include health_info when the target provided one
        if self._health_info is not None:
            metadata["health_info"] = self._health_info

        # Include explanation when the subclass provides one
        if self.explanation is not None:
            metadata["explanation"] = self.explanation

        # Merge any caller-supplied extra keys
        if extra:
            metadata.update(extra)

        return metadata

    def _check_execute_all_skip(self) -> list[TargetResult] | None:
        """Check whether this target should be skipped in execute_all().

        Replicates the two skip guards from execute() for use by
        PerHostTarget.execute_all() and PerServiceTarget.execute_all(),
        which bypass execute() and need the same logic.

        Returns:
            A single-element list of not-applicable TargetResults if the
            target should be skipped, or None if execution should proceed.
        """
        start_time: float = time.monotonic()

        # Source mode gate: skip targets whose source_mode doesn't match the runner
        is_client_run: bool = self.config.gathered_from == 'client'
        if is_client_run and self.source_mode == SourceMode.BACKEND:
            self.terminal.target_start(self._path)
            return [self._build_not_applicable_result(
                path=self._path,
                reason="Backend target, skipped in client mode",
                start_time=start_time,
            )]
        if not is_client_run and self.source_mode == SourceMode.CLIENT:
            self.terminal.target_start(self._path)
            return [self._build_not_applicable_result(
                path=self._path,
                reason="Client target, skipped in backend mode",
                start_time=start_time,
            )]

        # Cluster affinity gate
        if (
            self.config.cluster_type != 'both'
            and self.cluster_affinity != 'both'
            and self.config.cluster_type != self.cluster_affinity
        ):
            self.terminal.target_start(self._path)
            return [self._build_not_applicable_result(
                path=self._path,
                reason=(
                    f"Target has '{self.cluster_affinity}' cluster affinity, "
                    f"skipped for --cluster-type '{self.config.cluster_type}'"
                ),
                start_time=start_time,
            )]

        # When running from the admin host, targets that require internet can't work
        if self.config.gathered_from == 'admin-host' and self.requires_external_access:
            self.terminal.target_start(self._path)
            return [self._build_not_applicable_result(
                path=self._path,
                reason="Requires external internet access, unavailable from admin host",
                start_time=start_time,
            )]

        # When running in k8s-only mode, targets that require SSH can't work
        if self.config.only_through_kubernetes and self.requires_ssh:
            self.terminal.target_start(self._path)
            return [self._build_not_applicable_result(
                path=self._path,
                reason="Requires SSH access, unavailable in Kubernetes-only mode",
                start_time=start_time,
                extra_metadata={"only_through_kubernetes": True},
            )]

        return None

    def _build_not_applicable_result(
        self,
        path: str,
        reason: str,
        start_time: float,
        extra_metadata: dict[str, Any] | None = None,
        emit_not_applicable_line: bool = True,
    ) -> TargetResult:
        """Build a not_applicable TargetResult for a path that can't be collected.

        Shared helper used by PerServiceTarget.execute_all() (and any future
        callers) when collect_for_service() raises NotApplicableError. Produces
        the same sentinel structure as execute()'s own NotApplicableError handler
        so the UI greys the item out consistently.

        Args:
            path:           Data point path (e.g. 'kubernetes/pods/annotations/brig').
            reason:         Human-readable explanation from NotApplicableError.
            start_time:     Monotonic timestamp from before the collection attempt.
            extra_metadata: Additional keys merged into the metadata dict
                            (e.g. service_name for PerServiceTarget).
            emit_not_applicable_line:
                            Whether to print a terminal not_applicable line.
                            False when the caller already printed a target_start
                            header for this path.

        Returns:
            A successful TargetResult with not_applicable metadata.
        """
        if emit_not_applicable_line:
            self.terminal.target_not_applicable(path, reason)

        # Safe fallback for description
        try:
            na_description: str = self.description
        except NotImplementedError:
            na_description = ""

        # Build metadata using the shared helper, then add not_applicable fields
        na_metadata: dict[str, Any] = self._build_base_metadata(
            start_time,
            not_applicable=True,
            not_applicable_reason=reason,
        )

        # Merge caller-supplied keys (e.g. service_name, host_name)
        if extra_metadata:
            na_metadata.update(extra_metadata)

        duration_seconds: float = na_metadata["duration_seconds"]

        na_dp: DataPoint = DataPoint(
            path=path,
            value=None,
            unit=self.unit,
            description=na_description,
            raw_output="\n".join(self._raw_outputs),
            metadata=na_metadata,
        )

        return TargetResult(
            data_point=na_dp,
            success=True,
            error=None,
            duration_seconds=round(duration_seconds, 3),
        )

    def execute(self) -> TargetResult:
        """Execute this target with full error handling and output.

        The runner calls this. It prints the target start line, calls collect()
        in a try/except, records timing, builds the DataPoint with metadata,
        prints success or failure, returns a TargetResult. Don't override this.

        Returns:
            A TargetResult with the collected data or error information.
        """
        # Record start time for duration calculation
        start_time: float = time.monotonic()

        # Print the target header line
        self.terminal.target_start(self.path)

        # Show explanation of why this check exists and what it looks for
        if self.explanation is not None:
            self.terminal.target_explanation(self.explanation)

        # Clear accumulators so they don't leak from a previous run
        self._reset_accumulators()

        # Source mode gate: skip targets whose source_mode doesn't match the runner
        is_client_run: bool = self.config.gathered_from == 'client'
        if is_client_run and self.source_mode == SourceMode.BACKEND:
            return self._build_not_applicable_result(
                path=self.path,
                reason="Backend target, skipped in client mode",
                start_time=start_time,
            )
        if not is_client_run and self.source_mode == SourceMode.CLIENT:
            return self._build_not_applicable_result(
                path=self.path,
                reason="Client target, skipped in backend mode",
                start_time=start_time,
            )

        # Cluster affinity gate: skip targets whose affinity doesn't match
        # the --cluster-type parameter (unless cluster_type is «both»)
        if (
            self.config.cluster_type != 'both'
            and self.cluster_affinity != 'both'
            and self.config.cluster_type != self.cluster_affinity
        ):
            return self._build_not_applicable_result(
                path=self.path,
                reason=(
                    f"Target has '{self.cluster_affinity}' cluster affinity, "
                    f"skipped for --cluster-type '{self.config.cluster_type}'"
                ),
                start_time=start_time,
            )

        # when running from the admin host, targets that require internet can't work
        # (so we emit a sentinel data point so the UI can grey them out).
        if (
            self.config.gathered_from == 'admin-host'
            and self.requires_external_access
        ):
            return self._build_not_applicable_result(
                path=self.path,
                reason="Requires external internet access, unavailable from admin host",
                start_time=start_time,
            )

        # When running in k8s-only mode, targets that require SSH can't work
        # (emit a sentinel so the UI can grey them out).
        if (
            self.config.only_through_kubernetes
            and self.requires_ssh
        ):
            return self._build_not_applicable_result(
                path=self.path,
                reason="Requires SSH access, unavailable in Kubernetes-only mode",
                start_time=start_time,
                extra_metadata={"only_through_kubernetes": True},
            )

        try:
            # run the subclass collect() logic
            value: str | int | float | bool | None = self.collect()

            # dynamic description overrides static (if set)
            description: str = (
                self._dynamic_description
                if self._dynamic_description is not None
                else self.description
            )

            # build metadata using the shared helper
            metadata: dict[str, Any] = self._build_base_metadata(start_time)

            # build the DataPoint with all metadata
            data_point: DataPoint = DataPoint(
                path=self.path,
                value=value,
                unit=self.unit,
                description=description,
                raw_output="\n".join(self._raw_outputs),
                metadata=metadata,
            )

            # print the success line (green means we got data)
            self.terminal.target_success(self.path, value, self.unit)

            # show the health assessment if the target provided one
            if self._health_info is not None:
                self.terminal.health_info(self._health_info)

            return TargetResult(
                data_point=data_point,
                success=True,
                error=None,
                duration_seconds=metadata["duration_seconds"],
            )

        except NotApplicableError as na_error:
            # Target discovered at runtime that it can't collect data.
            # Emit a not_applicable sentinel so the UI greys it out and the
            # summary doesn't show a scary "collection failure" line.
            return self._build_not_applicable_result(
                path=self.path,
                reason=na_error.reason,
                start_time=start_time,
            )

        except Exception as error:
            # print the failure line
            self.terminal.target_failure(self.path, str(error))

            # try to get description (it might raise though)
            try:
                error_description: str = (
                    self._dynamic_description
                    if self._dynamic_description is not None
                    else self.description
                )
            except Exception:
                error_description = self._dynamic_description or ""

            # Build metadata using the shared helper, add error field
            error_metadata: dict[str, Any] = self._build_base_metadata(
                start_time, error=str(error),
            )

            error_dp: DataPoint = DataPoint(
                path=self.path,
                value=None,
                unit=self.unit,
                description=error_description,
                raw_output="\n".join(self._raw_outputs),
                metadata=error_metadata,
            )

            return TargetResult(
                data_point=error_dp,
                success=False,
                error=str(error),
                duration_seconds=error_metadata["duration_seconds"],
            )

    # ── Private helpers ──────────────────────────────────────────

    def _resolve_kubectl_docker_image(self) -> str:
        """Resolve the Docker image for running kubectl on the admin host.

        Three cases: empty string means kubectl runs directly, «auto» means detect
        the wire-server-deploy image on first call and cache it, anything else is
        the explicit Docker image name.

        Returns:
            Docker image string, or empty string if kubectl runs directly.
        """
        configured: str = self.config.kubernetes.docker_image

        # no docker wrapping
        if not configured:
            return ""

        # dry-run: skip SSH detection, return configured value as-is.
        # _build_kubectl_hops() handles the display label for 'auto'.
        if self.config.dry_run:
            return configured

        # explicit image name (not auto)
        if configured != "auto":
            return configured

        # fast path: already cached
        if BaseTarget._kubectl_docker_image is not None:
            return BaseTarget._kubectl_docker_image

        # grab the lock, re-check inside (only first thread does SSH detection,
        # others wait and pick up cached value).
        with BaseTarget._kubectl_docker_image_lock:
            if BaseTarget._kubectl_docker_image is not None:
                return BaseTarget._kubectl_docker_image

            # Detect the wire-server-deploy Docker image — locally when on the
            # admin host, via SSH otherwise.
            self.terminal.step("Auto-detecting kubectl Docker image on admin host...")
            detected: str
            if self.config.gathered_from == 'admin-host':
                detected = detect_kubectl_docker_image_local()
            else:
                admin_ssh: object = self.ssh.to(self.config.admin_host.ip)
                detected = detect_kubectl_docker_image(admin_ssh)

            if detected:
                self.terminal.step(f"Found kubectl image: {detected}")
                BaseTarget._kubectl_docker_image = detected
            else:
                self.terminal.step("No wire-server-deploy image found, kubectl runs directly")
                BaseTarget._kubectl_docker_image = ""

        return BaseTarget._kubectl_docker_image

    def _build_kubectl_ssh_target(self) -> SSHTarget | None:
        """Build an SSH target for remote kubectl execution.

        When kubernetes.route_via_ssh is True, kubectl runs on the admin host
        (typically inside a Docker container). If we're already on the admin host,
        kubectl runs locally (no SSH).

        Returns:
            An SSHTarget for the admin host, or None for local kubectl.
        """
        # When on the admin host, kubectl runs locally no SSH routing needed
        if self.config.gathered_from == 'admin-host':
            return None

        # Only route kubectl through SSH if explicitly configured
        if not self.config.kubernetes.route_via_ssh:
            return None

        # Direct SSH to admin host kubectl runs there (in Docker)
        return self.ssh.to(self.config.admin_host.ip)

    def discover_ingress_https_nodeport(self) -> int:
        """Discover the HTTPS NodePort for the ingress-nginx controller.

        Wire offline deployments expose the ingress via Kubernetes NodePort rather
        than a load balancer. This method runs kubectl once to find the NodePort
        for port 443 on the ingress-nginx service, caching the result for all
        subsequent calls.

        Returns:
            The NodePort number (e.g. 31773), or 0 if not found.
        """
        # Fast path: already cached
        if BaseTarget._ingress_https_nodeport is not None:
            return BaseTarget._ingress_https_nodeport

        with BaseTarget._ingress_nodeport_lock:
            # Re-check inside lock (another thread might have just finished)
            if BaseTarget._ingress_https_nodeport is not None:
                return BaseTarget._ingress_https_nodeport

            self.terminal.step("Discovering ingress HTTPS NodePort...")

            try:
                _result, parsed = self.run_kubectl(
                    'svc',
                    selector='app.kubernetes.io/name=ingress-nginx',
                    all_namespaces=True,
                )

                # Walk through the service list looking for the NodePort mapping
                if parsed and isinstance(parsed, dict):
                    items: list[dict[str, Any]] = parsed.get('items', [])
                    for item in items:
                        spec: dict[str, Any] = item.get('spec', {})
                        if spec.get('type') != 'NodePort':
                            continue
                        for port_entry in spec.get('ports', []):
                            if port_entry.get('port') == 443:
                                nodeport: int = port_entry.get('nodePort', 0)
                                if nodeport:
                                    self.terminal.step(
                                        f"Ingress HTTPS NodePort: {nodeport}"
                                    )
                                    BaseTarget._ingress_https_nodeport = nodeport
                                    return nodeport
            except Exception:
                pass

            # No NodePort found
            self.terminal.step("No ingress NodePort found")
            BaseTarget._ingress_https_nodeport = 0

        return 0

    def get_first_kube_node_ip(self) -> str:
        """Get the IP of the first available kube node.

        Uses config.nodes.kube_nodes if set, otherwise falls back to kubectl
        node discovery (same logic used by discover_vm_hosts). The kubectl
        result is cached at the class level so multiple targets don't each
        trigger a separate kubectl get nodes call.

        Returns:
            The first kube node IP, or empty string if none available.
        """
        # Prefer the explicit config list when provided
        if self.config.nodes.kube_nodes:
            return self.config.nodes.kube_nodes[0]

        # Check the class-level cache first (None = not yet attempted)
        if BaseTarget._discovered_kube_node_ip is not None:
            return BaseTarget._discovered_kube_node_ip

        # First caller discovers via kubectl under a lock
        with BaseTarget._kube_node_ip_lock:
            # Re-check after acquiring the lock (another thread may have populated it)
            if BaseTarget._discovered_kube_node_ip is not None:
                return BaseTarget._discovered_kube_node_ip

            # Use the shared kubectl node discovery helper
            ips: list[str] = discover_kube_node_ips(self.run_kubectl)
            BaseTarget._discovered_kube_node_ip = ips[0] if ips else ''

        return BaseTarget._discovered_kube_node_ip

    def _record_command(
        self,
        command: str,
        execution_type: str,
        hops: list[str] | None = None,
    ) -> bool:
        """Record a command for dry-run mode.

        When dry-run is active, appends a CommandRecord and returns True so the
        caller knows to return a synthetic result instead of executing. In normal
        mode, returns False (caller proceeds with real execution).

        Args:
            command: The command or query that would run.
            execution_type: Category ('local', 'ssh', 'kubectl', etc.).
            hops: Execution path steps. None defaults to ['local'].

        Returns:
            True if dry-run is active (caller should return early), False otherwise.
        """
        if not self.config.dry_run:
            return False

        self._dry_run_records.append(CommandRecord(
            target_path=self._path,
            command=command,
            execution_type=execution_type,
            hops=hops or ["local"],
        ))
        return True

    def _build_ssh_hops(self, host: str) -> list[str]:
        """Build the hop description for an SSH command to the given host.

        Mirrors the routing logic in run_ssh() so the dry-run table shows
        the same execution path that would be used in a real run.

        Args:
            host: Target host IP or hostname.

        Returns:
            List of hop descriptions (e.g. ['ssh deploy@10.0.0.1', 'ssh root@db']).
        """
        admin_user: str = self.config.admin_host.user
        admin_ip: str = self.config.admin_host.ip
        db_user: str = self.config.databases.ssh_user
        has_db_key: bool = bool(self.config.databases.ssh_key)

        if self.config.gathered_from == 'admin-host':
            if host == admin_ip:
                # already on admin host, runs locally
                return ["local"]
            elif has_db_key:
                # direct SSH with database credentials
                return [f"ssh {db_user}@{host}"]
            else:
                # direct SSH with admin credentials
                return [f"ssh {admin_user}@{host}"]
        elif has_db_key and host != admin_ip:
            # jump through admin host to reach private-network host
            return [f"ssh {admin_user}@{admin_ip}", f"ssh {db_user}@{host}"]
        else:
            # direct SSH with admin credentials
            return [f"ssh {admin_user}@{host}"]

    def _build_db_hops(self, db_host: str) -> list[str]:
        """Build the hop description for a database SSH command.

        Mirrors the routing logic in run_db_command().

        Args:
            db_host: Database host IP.

        Returns:
            List of hop descriptions.
        """
        admin_user: str = self.config.admin_host.user
        admin_ip: str = self.config.admin_host.ip
        db_user: str = self.config.databases.ssh_user
        has_db_key: bool = bool(self.config.databases.ssh_key)

        if self.config.gathered_from == 'admin-host':
            if has_db_key:
                return [f"ssh {db_user}@{db_host}"]
            else:
                return [f"ssh {admin_user}@{db_host}"]
        elif has_db_key:
            return [f"ssh {admin_user}@{admin_ip}", f"ssh {db_user}@{db_host}"]
        else:
            return [f"ssh {admin_user}@{db_host}"]

    def _build_kubectl_hops(self) -> list[str]:
        """Build the hop description for a kubectl command.

        Mirrors the routing logic in run_kubectl() / _build_kubectl_ssh_target().
        Includes docker wrapping when configured.

        Returns:
            List of hop descriptions.
        """
        admin_user: str = self.config.admin_host.user
        admin_ip: str = self.config.admin_host.ip
        hops: list[str] = []

        # SSH hop (when not on admin host and route_via_ssh is configured)
        if self.config.gathered_from != 'admin-host' and self.config.kubernetes.route_via_ssh:
            hops.append(f"ssh {admin_user}@{admin_ip}")
        else:
            hops.append("local")

        # Docker wrapping — in Wire offline deployments, kubectl runs inside a
        # Docker container (the wire-server-deploy image). When set to «auto»,
        # the image name is detected at runtime by running:
        #   docker images --format '{{.Repository}}:{{.Tag}}' | grep wire-server-deploy | head -1
        docker_image: str = self.config.kubernetes.docker_image
        if docker_image:
            if docker_image == "auto":
                display_image: str = "docker run <wire-server-deploy image>"
            else:
                display_image = f"docker run {docker_image}"
            hops.append(display_image)

        return hops

    def _build_cql_hops(self) -> list[str]:
        """Build the hop description for a CQL query via SSH tunnel.

        Mirrors the tunnel routing logic in run_cql_query().

        Returns:
            List of hop descriptions.
        """
        cassandra_host: str = self.config.databases.cassandra
        admin_user: str = self.config.admin_host.user
        admin_ip: str = self.config.admin_host.ip
        db_user: str = self.config.databases.ssh_user
        has_db_key: bool = bool(self.config.databases.ssh_key)

        if self.config.gathered_from == 'admin-host':
            if has_db_key:
                return [f"ssh tunnel {db_user}@{cassandra_host}:9042"]
            else:
                return [f"ssh tunnel {admin_user}@{cassandra_host}:9042"]
        elif has_db_key:
            return [f"ssh tunnel {admin_user}@{admin_ip} \u2192 {cassandra_host}:9042"]
        else:
            return [f"ssh tunnel {admin_user}@{cassandra_host}:9042"]

    @staticmethod
    def _empty_command_result(command_str: str = "") -> CommandResult:
        """Build a synthetic empty CommandResult for dry-run mode.

        Args:
            command_str: Command string for the result's command field.

        Returns:
            A CommandResult with empty output and success=True.
        """
        return CommandResult(
            command=command_str,
            exit_code=0,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            success=True,
            timed_out=False,
        )

    def _track_output(self, command_str: str, result_stdout: str) -> None:
        """Track command output for inclusion in the DataPoint.

        Appends stdout to _raw_outputs (if non-empty) and the command to _commands_run.
        Every command helper calls this to avoid duplication.

        Args:
            command_str: The command that was run (for metadata tracking).
            result_stdout: The stdout from the command execution.
        """
        # Only append non-empty output to avoid cluttering raw_output
        if result_stdout.strip():
            self._raw_outputs.append(result_stdout)

        # Always track the command regardless of output
        self._commands_run.append(command_str)

    # ── Command helpers ──────────────────────────────────────────

    def run_local(
        self,
        command: list[str],
        timeout: int | None = None,
        stdin_data: bytes | None = None,
    ) -> CommandResult:
        """Run a local command and track it for raw_output.

        Prints the command (verbose mode) and records the output for the data point.

        Args:
            command: Command and arguments as a list.
            timeout: Override default timeout from config.
            stdin_data: Raw bytes to feed into the process's stdin (for binary
                protocol probes like STUN).

        Returns:
            A CommandResult.

        Raises:
            CommandError: If the command fails and the target needs to abort.
        """
        # Show what action is being performed
        command_str: str = shlex.join(command)

        # Dry-run: record the command and return a synthetic result
        if self._record_command(command_str, "local"):
            return self._empty_command_result(command_str)

        self.terminal.step(f"Running: {command_str}")

        # Print the command in verbose mode
        self.terminal.command(command_str)

        # Execute the command with timeout fallback to config default
        effective_timeout: int = timeout if timeout is not None else self.config.timeout
        result: CommandResult = run_command(
            command, timeout=effective_timeout, stdin_data=stdin_data,
        )

        # Show compacted output summary so operator sees what came back
        self.terminal.command_result(result.stdout)

        # Print full output in verbose mode
        self.terminal.command_output(result.stdout)

        # Track output for the DataPoint
        self._track_output(command_str, result.stdout)

        return result

    def run_ssh(self, host: str, command: str, timeout: int | None = None) -> CommandResult:
        """Run a command on a remote host via SSH.

        If databases.ssh_key is configured and we're not the admin host, routes through
        the admin host as a jump host (handles private-network hosts transparently).

        Args:
            host: Remote host IP or hostname.
            command: Command to run on the remote host.
            timeout: Override default timeout.

        Returns:
            A CommandResult.
        """
        # Dry-run: record with the routing hops and return synthetic result
        if self._record_command(command, "ssh", self._build_ssh_hops(host)):
            return self._empty_command_result(f"ssh {host} {command}")

        # show what we're doing
        self.terminal.step(f"SSH to {host}: {command}")

        # print the ssh command (verbose mode)
        self.terminal.command(
            f"ssh {self.config.admin_host.user}@{host} {command}"
        )

        # if we're on the admin host, routing is different. SSHing to the admin host
        # itself means run it locally (we're already there). SSHing to internal hosts,
        # we go direct with db creds. If we're not on the admin host, route through
        # it as a jump host if we need to.
        local_timeout: int = timeout if timeout is not None else self.config.timeout
        if self.config.gathered_from == 'admin-host':
            if host == self.config.admin_host.ip:
                # already on admin host, run locally
                result: CommandResult = run_command(
                    ['sh', '-c', command],
                    timeout=local_timeout,
                )
            elif self.config.databases.ssh_key:
                # private-network host, reach it directly (db key is local)
                result = self.ssh.db_to(host).run(command, timeout=local_timeout)
            else:
                # directly reachable, use admin credentials
                result = self.ssh.to(host).run(command, timeout=local_timeout)
        elif self.config.databases.ssh_key and host != self.config.admin_host.ip:
            result = self.ssh.via(self.config.admin_host.ip).to(host).run(command, timeout=local_timeout)
        else:
            result = self.ssh.to(host).run(command, timeout=local_timeout)

        # Show compacted output summary
        self.terminal.command_result(result.stdout)

        # Print full output in verbose mode
        self.terminal.command_output(result.stdout)

        # Track output for the DataPoint
        self._track_output(f"ssh {host} {command}", result.stdout)

        return result

    def run_kubectl(
        self,
        resource: str,
        namespace: str | None = None,
        selector: str | None = None,
        all_namespaces: bool = False,
    ) -> tuple[CommandResult, Any]:
        """Run kubectl get and parse JSON output.

        Uses the config's kubernetes namespace by default.

        Args:
            resource: Resource type (e.g., 'nodes', 'pods').
            namespace: Override namespace. None = use config default.
            selector: Label selector.
            all_namespaces: Search all namespaces.

        Returns:
            Tuple of (CommandResult, parsed_json).
        """
        # Resolve namespace use config default when not explicitly provided
        resolved_namespace: str | None = (
            namespace if namespace is not None else self.config.cluster.kubernetes_namespace
        )

        # Build a display command string for terminal output
        display_parts: list[str] = ["kubectl", "get", resource]
        if all_namespaces:
            display_parts.append("--all-namespaces")
        elif resolved_namespace:
            display_parts.extend(["-n", resolved_namespace])
        if selector:
            display_parts.extend(["-l", selector])
        display_parts.append("-o json")
        display_cmd: str = " ".join(display_parts)

        # Dry-run: record the kubectl command and return empty parsed result
        if self._record_command(display_cmd, "kubectl", self._build_kubectl_hops()):
            return self._empty_command_result(display_cmd), {}

        # Show what action is being performed
        self.terminal.step(f"kubectl get {resource}")
        self.terminal.command(display_cmd)

        # Build SSH target and resolve Docker image for kubectl execution.
        # Docker image must be resolved unconditionally — when running on the
        # admin host (ssh_target=None), kubectl still needs the Docker wrapper
        # because kubectl is only available inside the wire-server-deploy container.
        ssh_target: object = self._build_kubectl_ssh_target()
        docker_image: str = self._resolve_kubectl_docker_image()

        # Execute kubectl get with JSON output
        result: CommandResult
        parsed: Any
        result, parsed = kubectl_get(
            resource=resource,
            namespace=resolved_namespace,
            selector=selector,
            all_namespaces=all_namespaces,
            timeout=self.config.timeout,
            context=self.config.kubernetes_context,
            ssh_target=ssh_target,
            docker_image=docker_image,
            admin_home=self.config.kubernetes.admin_home,
        )

        # Show per-item summaries for kubectl JSON output instead of raw JSON
        if parsed and isinstance(parsed, dict):
            if "items" in parsed:
                items: list[Any] = parsed["items"]
                summary: str = "\n".join(
                    summarize_kubectl_item(item) for item in items
                )
                self.terminal.command_result(summary or "(empty list)")
            else:
                # Single-resource response (e.g. configmap/foo)
                self.terminal.command_result(summarize_kubectl_item(parsed))
        else:
            self.terminal.command_result(result.stdout)

        # Track output for the DataPoint
        self._track_output(display_cmd, result.stdout)

        return result, parsed

    def run_kubectl_raw(self, args: list[str]) -> CommandResult:
        """Run an arbitrary kubectl command.

        Args:
            args: kubectl arguments.

        Returns:
            A CommandResult.
        """
        # Build display string from args
        args_str: str = " ".join(args)
        display_cmd: str = f"kubectl {args_str}"

        # Dry-run: record and return synthetic result
        if self._record_command(display_cmd, "kubectl", self._build_kubectl_hops()):
            return self._empty_command_result(display_cmd)

        # Show what action is being performed
        self.terminal.step(display_cmd)

        # Print the command in verbose mode
        self.terminal.command(display_cmd)

        # Build SSH target and resolve Docker image for kubectl execution.
        # Docker image must be resolved unconditionally — when running on the
        # admin host (ssh_target=None), kubectl still needs the Docker wrapper
        # because kubectl is only available inside the wire-server-deploy container.
        ssh_target: object = self._build_kubectl_ssh_target()
        docker_image: str = self._resolve_kubectl_docker_image()

        # Execute the raw kubectl command
        result: CommandResult = kubectl_raw(
            args=args,
            timeout=self.config.timeout,
            context=self.config.kubernetes_context,
            ssh_target=ssh_target,
            docker_image=docker_image,
            admin_home=self.config.kubernetes.admin_home,
        )

        # Show compacted output summary
        self.terminal.command_result(result.stdout)

        # Track output for the DataPoint
        self._track_output(f"kubectl {args_str}", result.stdout)

        return result

    def run_db_command(self, db_host: str, command: str) -> CommandResult:
        """Run a command on a database host via SSH.

        If databases.ssh_key is configured, routes through the admin host
        as a jump host (for private-network database VMs). Otherwise,
        connects directly to the database host.

        Args:
            db_host: Database host IP from config (e.g., config.databases.cassandra).
            command: Command to run.

        Returns:
            A CommandResult.
        """
        # Dry-run: record with database routing hops
        if self._record_command(command, "db-ssh", self._build_db_hops(db_host)):
            return self._empty_command_result(f"ssh {db_host} {command}")

        # Show what action is being performed
        self.terminal.step(f"DB command on {db_host}: {command}")

        # When running ON the admin host, connect directly to database hosts -
        # no jump hop needed since the db SSH key is a local file here.
        if self.config.gathered_from == 'admin-host':
            if self.config.databases.ssh_key:
                result: CommandResult = self.ssh.db_to(db_host).run(command)
            else:
                result = self.ssh.to(db_host).run(command)
        # If database SSH key is set, route through admin host as jump host
        elif self.config.databases.ssh_key:
            result = self.ssh.via(self.config.admin_host.ip).to(db_host).run(command)
        else:
            result = self.ssh.to(db_host).run(command)

        # Show compacted output summary
        self.terminal.command_result(result.stdout)

        # Print full output in verbose mode
        self.terminal.command_output(result.stdout)

        # Surface stderr when non-empty helps diagnose failures like
        # cqlsh auth errors or missing binaries that would otherwise be invisible
        if result.stderr.strip():
            self.terminal.command_stderr(result.stderr)

        # Track output for the DataPoint
        self._track_output(f"ssh {db_host} {command}", result.stdout)

        return result

    def run_cql_query(self, cql: str) -> CqlResult:
        """Run a CQL query against Cassandra using the native protocol.

        Opens an SSH tunnel to the Cassandra node's port 9042, uses our pure-Python
        CQL client to execute the query and return structured results. No cqlsh needed,
        no Python on the remote host.

        Tunnel routing depends on network topology. Private network (databases.ssh_key set):
        SSH to the admin host and forward to cassandra_host:9042. Direct network:
        SSH directly to the Cassandra host and forward to localhost:9042.

        Args:
            cql: CQL query string (e.g.,
                 «SELECT keyspace_name FROM system_schema.keyspaces»).

        Returns:
            CqlResult with columns and rows.

        Raises:
            CqlConnectionError: If the tunnel or connection fails.
            CqlError: If the query itself fails.
        """
        # Dry-run: record the CQL query with tunnel routing info
        if self._record_command(f"CQL: {cql}", "cql", self._build_cql_hops()):
            return CqlResult(columns=[], rows=[])

        cassandra_host: str = self.config.databases.cassandra

        self.terminal.step(f"CQL query via tunnel to {cassandra_host}:9042")

        # tunnel params depend on network topology and where we're running.
        # if we're on the admin host, db SSH key is a local file, so SSH directly
        # to the Cassandra node and forward localhost:9042. Works for both
        # private-network and direct deployments.
        # if we're exterior: private network means SSH to admin host and forward
        # to cassandra:9042 (admin sits on the private network). Direct network
        # means SSH to Cassandra host itself and forward localhost:9042.
        if self.config.gathered_from == 'admin-host':
            if self.config.databases.ssh_key:
                # private-network deploy (db SSH key is now a local path)
                tunnel: SSHTunnel = SSHTunnel(
                    remote_host='127.0.0.1',
                    remote_port=9042,
                    ssh_host=cassandra_host,
                    ssh_user=self.config.databases.ssh_user,
                    ssh_key=self.config.databases.ssh_key,
                    ssh_port=self.config.databases.ssh_port,
                )
            else:
                # direct-network deploy (use admin creds to reach Cassandra)
                tunnel = SSHTunnel(
                    remote_host='127.0.0.1',
                    remote_port=9042,
                    ssh_host=cassandra_host,
                    ssh_user=self.config.admin_host.user,
                    ssh_key=self.config.admin_host.ssh_key,
                    ssh_port=self.config.admin_host.ssh_port,
                )
        elif self.config.databases.ssh_key:
            # exterior + private network: SSH to admin host, forward to cassandra:9042.
            # admin sits on the private network, can reach cassandra directly.
            tunnel = SSHTunnel(
                remote_host=cassandra_host,
                remote_port=9042,
                ssh_host=self.config.admin_host.ip,
                ssh_user=self.config.admin_host.user,
                ssh_key=self.config.admin_host.ssh_key,
                ssh_port=self.config.admin_host.ssh_port,
            )
        else:
            # exterior + direct network: SSH to Cassandra host, forward localhost:9042
            tunnel = SSHTunnel(
                remote_host='127.0.0.1',
                remote_port=9042,
                ssh_host=cassandra_host,
                ssh_user=self.config.admin_host.user,
                ssh_key=self.config.admin_host.ssh_key,
                ssh_port=self.config.admin_host.ssh_port,
            )

        with tunnel:
            self.terminal.step(
                f"Tunnel open on localhost:{tunnel.local_port} → "
                f"{cassandra_host}:9042"
            )

            # show the query like we show other commands
            self.terminal.command(f"CQL: {cql}")

            with CqlClient(
                host='127.0.0.1',
                port=tunnel.local_port,
                username=self.config.databases.cassandra_username,
                password=self.config.databases.cassandra_password,
            ) as client:
                result: CqlResult = client.query(cql)

        # format results as readable text
        display_output: str = format_cql_result(result)

        # show the result like we show SSH output
        self.terminal.command_result(display_output)

        # track for metadata
        self._track_output(f"CQL: {cql}", display_output)

        return result

    @staticmethod
    def _cqlsh_file_command(query: str, cqlsh_prefix: str) -> str:
        """Build a shell command that writes a CQL query to a temp file, runs it, and cleans up.

        Uses a single-quoted heredoc so the query is never parsed by the
        shell — no escaping of double quotes, $, backticks, etc. is needed.

        Args:
            query: Raw CQL query string.
            cqlsh_prefix: The cqlsh invocation prefix (e.g. "cqlsh" or "cqlsh 10.0.0.1").

        Returns:
            A shell command string safe for any query content.
        """
        # Single-quoted heredoc delimiter ('CQLEOF') prevents all shell expansion
        return (
            f"_qf=$(mktemp /tmp/cqlsh_query.XXXXXX) && "
            f"cat <<'CQLEOF' > \"$_qf\"\n{query}\nCQLEOF\n"
            f"{cqlsh_prefix} -f \"$_qf\"; _rc=$?; rm -f \"$_qf\"; exit $_rc"
        )

    def run_cqlsh(self, query: str) -> CommandResult:
        """Run a cqlsh command as a fallback when native CQL is unavailable.

        Tries cqlsh in three locations:
        1. On the Cassandra node — tries both default host and localhost
        2. On the admin host — connects to Cassandra over the network
        3. Inside the wire-server-deploy Docker container — for environments
           where cqlsh isn't installed on the host but is available in Docker

        Stderr from the Cassandra node attempt is captured and shown as a
        warning (common: "No appropriate python interpreter found") so
        operators can diagnose fallback reasons.

        The query is written to a temp file and executed via cqlsh -f
        to avoid shell-escaping issues with CQL identifiers (double
        quotes), dollar signs, or backticks in the query string.

        Args:
            query: cqlsh query string (e.g., "DESCRIBE KEYSPACES").

        Returns:
            CommandResult from the first method that produces output.
            If all fail, returns the last result so the caller can
            inspect stderr.
        """
        cassandra_host: str = self.config.databases.cassandra

        # Attempt 1: cqlsh on the Cassandra node itself.
        # Capture stderr so we can show it as a warning if cqlsh fails
        # (common: "No appropriate python interpreter found").
        self.terminal.step(f"Falling back to cqlsh on {cassandra_host}...")
        db_cmd: str = (
            f'{self._cqlsh_file_command(query, "cqlsh")}'
            f' || {self._cqlsh_file_command(query, "cqlsh localhost")}'
        )
        db_result: CommandResult = self.run_db_command(cassandra_host, db_cmd)

        if db_result.stdout.strip():
            return db_result

        # Surface stderr as a warning so operators know why cqlsh failed
        if db_result.stderr.strip():
            self.terminal.warning(db_result.stderr.strip().split('\n')[0])

        # Attempt 2: cqlsh from the admin host, connecting to Cassandra
        # over the network (port 9042). This works when the Cassandra
        # node lacks Python but the admin host has cqlsh installed.
        self.terminal.step(
            f"cqlsh unavailable on {cassandra_host}, trying from admin host..."
        )

        admin_cmd: str = self._cqlsh_file_command(query, f'cqlsh {cassandra_host}')
        admin_result: CommandResult = self.run_ssh(
            self.config.admin_host.ip,
            admin_cmd,
        )

        if admin_result.stdout.strip():
            return admin_result

        # Attempt 3: cqlsh inside the wire-server-deploy Docker container.
        # In managed Wire deployments, cqlsh may only be available inside
        # the container image, not on the host OS.
        docker_image: str = self._resolve_kubectl_docker_image()
        if docker_image:
            self.terminal.step(
                f"cqlsh unavailable on admin host, trying via Docker..."
            )
            docker_cqlsh_cmd: str = (
                f"_qf=$(mktemp /tmp/cqlsh_query.XXXXXX) && "
                f"cat <<'CQLEOF' > \"$_qf\"\n{query}\nCQLEOF\n"
                f"docker run --rm --network=host"
                f" -v \"$_qf\":/tmp/cqlsh_query.cql:ro"
                f" {docker_image}"
                f" cqlsh {cassandra_host}"
                f" -f /tmp/cqlsh_query.cql"
                f"; _rc=$?; rm -f \"$_qf\"; exit $_rc"
            )
            docker_result: CommandResult = self.run_ssh(
                self.config.admin_host.ip,
                docker_cqlsh_cmd,
            )

            if docker_result.stdout.strip():
                return docker_result

        return admin_result

    def http_get(self, url: str, timeout: int = 15) -> HttpResult:
        """Make a direct HTTP GET request.

        Args:
            url: URL to request.
            timeout: Request timeout.

        Returns:
            An HttpResult.
        """
        # Dry-run: record the HTTP request
        if self._record_command(f"GET {url}", "http"):
            return HttpResult(
                url=url,
                status_code=0,
                body="",
                headers={},
                duration_seconds=0.0,
                success=True,
                error=None,
            )

        # Show what action is being performed
        self.terminal.step(f"HTTP GET {url}")

        # Execute the HTTP GET request
        result: HttpResult = http_get(url=url, timeout=timeout)

        # Track body on success, error message on failure
        tracked_output: str = result.body if result.success else (result.error or "")

        # Show compacted output summary
        self.terminal.command_result(tracked_output)

        self._track_output(f"GET {url}", tracked_output)

        return result

    def http_get_via_ssh(self, url: str, ssh_host: str) -> CommandResult:
        """Make an HTTP GET request through SSH to a remote host.

        Args:
            url: URL to request (as seen from the SSH host).
            ssh_host: Host to SSH into for making the request.

        Returns:
            A CommandResult with curl output.
        """
        # Dry-run: record with SSH routing to the host
        if self._record_command(
            f"curl {url}", "http-via-ssh", self._build_ssh_hops(ssh_host),
        ):
            return self._empty_command_result(f"ssh {ssh_host} curl {url}")

        # Show what action is being performed
        self.terminal.step(f"HTTP GET {url} via SSH to {ssh_host}")

        # Execute curl on the remote host via SSH
        result: CommandResult = http_get_via_ssh(
            url=url,
            ssh_host=ssh_host,
            config=self.config,
        )

        # Show compacted output summary
        self.terminal.command_result(result.stdout)

        # Track output for the DataPoint
        self._track_output(f"ssh {ssh_host} curl {url}", result.stdout)

        return result
