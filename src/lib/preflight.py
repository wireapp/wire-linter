"""Pre-flight connectivity checks for the Wire Fact Gathering Tool.

Verifies that the configuration actually works SSH keys authenticate,
hosts are reachable, and Kubernetes is accessible before running any
targets. Runs once at startup and bails early if anything fails.

Checks run in dependency order:
  1. SSH admin host (when gathered_from='external'; skipped otherwise)
  2. SSH database VMs (each unique DB host; routed correctly per mode)
  3. Kubernetes access (kubectl get nodes; routing based on config)

If the admin host SSH fails and later checks need to route through it,
they're automatically marked skipped rather than attempted. This avoids
confusing secondary failures that stem from the same underlying problem.

Classes:
    PreflightResult  immutable outcome of a single check
    PreflightChecker runs and reports all checks

Related modules:
    src/lib/ssh.py       SSH builder for admin host and jump-hop routing
    src/lib/kubectl.py   kubectl execution and docker image detection
    src/lib/config.py    typed configuration with all host/key details
    src/lib/terminal.py  terminal output (check_pass/fail/skip methods)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.lib.command import CommandResult
from src.lib.kubectl import kubectl_get, detect_kubectl_docker_image, detect_kubectl_docker_image_local
from src.lib.ssh import SSH, SSHTarget

if TYPE_CHECKING:
    from src.lib.config import Config
    from src.lib.logger import Logger
    from src.lib.terminal import Terminal


@dataclass
class PreflightResult:
    """Outcome of a single pre-flight connectivity check.

    Attributes:
        name:        Short name of the check (e.g., "SSH admin host").
        detail:      Context shown in parentheses (e.g., "deploy@10.0.0.1:22").
        success:     True if the check passed.
        message:     One-line outcome success detail or error text.
        skipped:     True when the check wasn't run due to a failed dependency.
        skip_reason: Why it was skipped (only meaningful when skipped is True).
    """

    name:        str
    detail:      str
    success:     bool
    message:     str
    skipped:     bool = False
    skip_reason: str  = ""


class PreflightChecker:
    """Runs pre-flight connectivity checks and reports pass/fail/skip results.

    Checks run in dependency order. When the admin host SSH check fails,
    any subsequent checks that need to route through it are automatically
    skipped instead of attempted, so you don't get confusing secondary failures.

    Usage:
        checker = PreflightChecker(config, terminal, logger)
        results = checker.run_checks()
        all_ok = all(r.success or r.skipped for r in results)
    """

    def __init__(
        self,
        config:   'Config',
        terminal: 'Terminal',
        logger:   'Logger',
    ) -> None:
        """Initialize the checker with config, terminal, and logger."""
        self._config:   'Config'   = config
        self._terminal: 'Terminal' = terminal
        self._logger:   'Logger'   = logger
        self._ssh:      SSH        = SSH(config)

    def run_checks(self) -> list[PreflightResult]:
        """Run all pre-flight checks in dependency order.

        Prints results as they complete, then a summary showing either
        «all passed» or how many failed.

        Returns:
            List of PreflightResult, one per check attempted or skipped.
        """
        results: list[PreflightResult] = []

        self._terminal.header("Pre-flight Checks")
        self._terminal.blank_line()

        # ── Check 1: SSH to admin host ──────────────────────────────────────
        # Skip this if we're already on the admin host.
        admin_ssh_ok: bool
        if self._config.gathered_from == 'admin-host':
            admin_check: PreflightResult = PreflightResult(
                name        = "SSH - admin host",
                detail      = (
                    f"{self._config.admin_host.user}@"
                    f"{self._config.admin_host.ip}:"
                    f"{self._config.admin_host.ssh_port}"
                ),
                success     = True,
                message     = "",
                skipped     = True,
                skip_reason = "running directly on admin host",
            )
            admin_ssh_ok = True
        else:
            admin_check = self._check_ssh_admin_host()
            admin_ssh_ok = admin_check.success

        results.append(admin_check)
        self._print_result(admin_check)

        # ── Check 2: SSH to database VMs ────────────────────────────────────
        # Check each unique DB host with the same routing targets use.
        # In kubernetes-only mode we never SSH to database VMs, so skip these.
        if not self._config.only_through_kubernetes:
            db_checks: list[PreflightResult] = self._check_database_vms(admin_ssh_ok)
            for check in db_checks:
                results.append(check)
                self._print_result(check)

        # ── Check 3: Kubernetes access ──────────────────────────────────────
        # We'll extract node IPs from the parsed JSON below if needed.
        kube_check: PreflightResult
        kubectl_parsed: dict | None
        kube_check, kubectl_parsed = self._check_kubernetes(admin_ssh_ok)
        results.append(kube_check)
        self._print_result(kube_check)

        # ── Checks 4+: SSH to each kube node and data node ──────────────────
        # Make sure we can actually SSH to every VM that targets will use.
        # Kube nodes come from config.nodes.kube_nodes or kubectl discovery.
        # Data nodes come from config.nodes.data_nodes or database host IPs.
        # In kubernetes-only mode we never SSH to any VM nodes, so skip these.
        if not self._config.only_through_kubernetes:
            vm_checks: list[PreflightResult] = self._check_vm_nodes(
                admin_ssh_ok, kubectl_parsed
            )
            for check in vm_checks:
                results.append(check)
                self._print_result(check)

        # ── Summary line ────────────────────────────────────────────────────
        self._terminal.blank_line()
        failed: list[PreflightResult] = [
            r for r in results if not r.success and not r.skipped
        ]
        if failed:
            self._terminal.error(
                f"{len(failed)} pre-flight check(s) failed - "
                "fix the above issues before running targets"
            )
        else:
            self._terminal.info("All pre-flight checks passed")

        self._terminal.blank_line()
        return results

    # ── Check implementations ────────────────────────────────────────────────

    def _check_ssh_admin_host(self) -> PreflightResult:
        """Verify SSH connectivity to the admin host.

        Runs «echo preflight_ok» on the admin host. Success needs both
        exit code 0 and «preflight_ok» in stdout.

        Returns:
            PreflightResult indicating success or failure.
        """
        ip:   str = self._config.admin_host.ip
        user: str = self._config.admin_host.user
        port: int = self._config.admin_host.ssh_port
        detail: str = f"{user}@{ip}:{port}"

        try:
            result: CommandResult = self._ssh.to(ip).run("echo preflight_ok")
            if result.exit_code == 0 and "preflight_ok" in result.stdout:
                return PreflightResult(
                    name    = "SSH - admin host",
                    detail  = detail,
                    success = True,
                    message = "connected",
                )

            # Non-zero exit or unexpected output surface the first error line
            error_text: str = (
                result.stderr.strip().splitlines()[0]
                if result.stderr.strip()
                else f"unexpected output (exit {result.exit_code})"
            )
            return PreflightResult(
                name    = "SSH - admin host",
                detail  = detail,
                success = False,
                message = error_text,
            )

        except Exception as exc:
            return PreflightResult(
                name    = "SSH - admin host",
                detail  = detail,
                success = False,
                message = str(exc),
            )

    def _check_database_vms(self, admin_ssh_ok: bool) -> list[PreflightResult]:
        """Verify SSH connectivity to each unique database VM.

        Deduplicates by IP when cassandra and rabbitmq share the same host,
        only one check runs. Routing logic mirrors run_db_command() in BaseTarget:
          external + ssh_key set  jump through admin host
          external + no ssh_key   direct SSH with admin credentials
          admin-host + ssh_key    direct SSH with db credentials
          admin-host + no ssh_key direct SSH with admin credentials

        If routing needs the admin host but admin_ssh_ok is False, we skip
        the check rather than attempt it.

        Args:
            admin_ssh_ok: Whether the admin host SSH check succeeded.

        Returns:
            List of PreflightResult, one per unique database host.
        """
        db = self._config.databases

        # Build a stable deduplicated list of (name, host) pairs
        seen_hosts: set[str]          = set()
        unique_hosts: list[tuple[str, str]] = []
        for db_name in ('cassandra', 'elasticsearch', 'minio', 'postgresql', 'rabbitmq'):
            host: str = getattr(db, db_name, '')
            if host and host not in seen_hosts:
                seen_hosts.add(host)
                unique_hosts.append((db_name, host))

        results: list[PreflightResult] = []

        for db_name, host in unique_hosts:
            # The detail label shows which credentials and port are being tested
            if db.ssh_key:
                detail: str = f"{db.ssh_user}@{host}:{db.ssh_port}"
            else:
                detail = (
                    f"{self._config.admin_host.user}@{host}:"
                    f"{self._config.admin_host.ssh_port}"
                )

            # When external and using a jump, skip if the admin host is unreachable
            needs_jump: bool = (
                self._config.gathered_from != 'admin-host'
                and bool(db.ssh_key)
            )
            if needs_jump and not admin_ssh_ok:
                results.append(PreflightResult(
                    name        = f"SSH - {db_name} VM",
                    detail      = detail,
                    success     = False,
                    message     = "",
                    skipped     = True,
                    skip_reason = "admin host SSH failed",
                ))
                continue

            try:
                cmd_result: CommandResult
                if self._config.gathered_from == 'admin-host':
                    # On the admin host connect directly to DB VMs
                    if db.ssh_key:
                        cmd_result = self._ssh.db_to(host).run("echo preflight_ok")
                    else:
                        cmd_result = self._ssh.to(host).run("echo preflight_ok")
                elif db.ssh_key:
                    # External with private-network VMs route via admin host
                    cmd_result = self._ssh.via(
                        self._config.admin_host.ip
                    ).to(host).run("echo preflight_ok")
                else:
                    # External with directly reachable VMs no jump needed
                    cmd_result = self._ssh.to(host).run("echo preflight_ok")

                if cmd_result.exit_code == 0 and "preflight_ok" in cmd_result.stdout:
                    results.append(PreflightResult(
                        name    = f"SSH - {db_name} VM",
                        detail  = detail,
                        success = True,
                        message = "connected",
                    ))
                else:
                    error_text: str = (
                        cmd_result.stderr.strip().splitlines()[0]
                        if cmd_result.stderr.strip()
                        else f"unexpected output (exit {cmd_result.exit_code})"
                    )
                    results.append(PreflightResult(
                        name    = f"SSH - {db_name} VM",
                        detail  = detail,
                        success = False,
                        message = error_text,
                    ))

            except Exception as exc:
                results.append(PreflightResult(
                    name    = f"SSH - {db_name} VM",
                    detail  = detail,
                    success = False,
                    message = str(exc),
                ))

        return results

    def _check_kubernetes(
        self,
        admin_ssh_ok: bool,
    ) -> tuple[PreflightResult, dict | None]:
        """Verify Kubernetes access by running kubectl get nodes.

        Routes kubectl the same way BaseTarget._build_kubectl_ssh_target() does:
          external + ssh_key set kubectl runs on admin host (via SSH)
          external + no ssh_key  kubectl runs locally
          admin-host             kubectl runs locally

        When docker_image is 'auto', we detect the wire-server-deploy image
        from the admin host. This detection is local only BaseTarget will
        detect and cache it independently on its first kubectl call.

        If kubectl needs the admin host and that SSH check failed, we skip this.

        Args:
            admin_ssh_ok: Whether the admin host SSH check passed.

        Returns:
            Tuple of (PreflightResult, parsed_json). parsed_json is the
            kubectl nodes JSON dict on success, None otherwise. _check_vm_nodes()
            uses this to extract node IPs when config.nodes.kube_nodes is unset.
        """
        # Determine if kubectl must route through the admin host.
        # Uses the dedicated kubernetes.route_via_ssh flag, which is decoupled
        # from databases.ssh_key (that controls the inner hop to DB VMs).
        needs_admin_ssh: bool = (
            self._config.gathered_from != 'admin-host'
            and self._config.kubernetes.route_via_ssh
        )

        if needs_admin_ssh and not admin_ssh_ok:
            return (
                PreflightResult(
                    name        = "Kubernetes - kubectl get nodes",
                    detail      = f"via {self._config.admin_host.ip}",
                    success     = False,
                    message     = "",
                    skipped     = True,
                    skip_reason = "admin host SSH failed",
                ),
                None,
            )

        # Build the SSH target for remote kubectl execution
        ssh_target: SSHTarget | None = None
        if needs_admin_ssh:
            ssh_target = self._ssh.to(self._config.admin_host.ip)

        # Resolve Docker image for kubectl
        docker_image: str = self._config.kubernetes.docker_image
        if docker_image == 'auto':
            if ssh_target is not None:
                # Detect by SSHing to the admin host and listing docker images
                detected: str = detect_kubectl_docker_image(ssh_target)
                docker_image = detected  # Empty string → run kubectl directly
            else:
                # Running locally (admin-host mode) — detect the image on this machine
                detected = detect_kubectl_docker_image_local()
                docker_image = detected

        # Build the detail label for terminal output
        if ssh_target is not None:
            route: str = f"via {self._config.admin_host.ip}"
        else:
            route = "local"

        detail: str
        if docker_image:
            # Show only the image name (strip registry prefix) to keep it compact
            short_image: str = docker_image.split('/')[-1][:35]
            detail = f"{route}, image: {short_image}"
        else:
            detail = route

        try:
            result: CommandResult
            parsed: object
            result, parsed = kubectl_get(
                resource     = "nodes",
                timeout      = self._config.timeout,
                context      = self._config.kubernetes_context,
                ssh_target   = ssh_target,
                docker_image = docker_image,
                admin_home   = self._config.kubernetes.admin_home,
            )

            if result.exit_code == 0 and isinstance(parsed, dict):
                items: list = parsed.get("items", [])
                node_count: int = len(items)
                return (
                    PreflightResult(
                        name    = "Kubernetes - kubectl get nodes",
                        detail  = detail,
                        success = True,
                        message = f"{node_count} node(s) found",
                    ),
                    parsed,
                )

            # Command ran but returned non-zero exit or unparseable output
            error_text: str
            if result.stderr.strip():
                error_text = result.stderr.strip().splitlines()[0]
            elif result.stdout.strip():
                error_text = result.stdout.strip().splitlines()[0]
            else:
                error_text = f"exit code {result.exit_code}"

            return (
                PreflightResult(
                    name    = "Kubernetes - kubectl get nodes",
                    detail  = detail,
                    success = False,
                    message = error_text,
                ),
                None,
            )

        except Exception as exc:
            return (
                PreflightResult(
                    name    = "Kubernetes - kubectl get nodes",
                    detail  = detail,
                    success = False,
                    message = str(exc),
                ),
                None,
            )

    def _check_vm_nodes(
        self,
        admin_ssh_ok: bool,
        kubectl_parsed: dict | None,
    ) -> list[PreflightResult]:
        """Verify SSH connectivity to every kube node and data node.

        Mirrors discover_vm_hosts() logic so we check exactly the VMs that
        vm/* targets will SSH into:

          Kube nodes:
            config.nodes.kube_nodes if non-empty
            otherwise: InternalIP from each kubectl node

          Data nodes:
            config.nodes.data_nodes if non-empty
            otherwise: unique IPs from databases.{cassandra,elasticsearch,minio,postgresql}

        IPs in both groups are checked once (kubenode label wins).

        SSH routing mirrors run_ssh() in BaseTarget:
          external + ssh_key set  jump via admin host (skip if admin failed)
          external + no ssh_key   direct SSH with admin credentials
          admin-host + ssh_key    direct SSH with db credentials
          admin-host + no ssh_key direct SSH with admin credentials

        Args:
            admin_ssh_ok:   Whether the admin host SSH check passed.
                            Controls whether jump-routed checks are skipped.
            kubectl_parsed: Parsed kubectl get nodes JSON, or None if that
                            check failed. Used to discover kube node IPs when
                            config.nodes.kube_nodes is unset.

        Returns:
            List of PreflightResult, one per unique VM node.
        """
        db = self._config.databases

        # ── Discover the full node list (mirrors discover_vm_hosts logic) ──
        seen_ips: set[str]                   = set()
        hosts:    list[tuple[str, str, str]] = []  # (role, label, ip)

        # Kube nodes first
        if self._config.nodes.kube_nodes:
            for ip in self._config.nodes.kube_nodes:
                if ip not in seen_ips:
                    hosts.append(("kube", f"kubenode-{ip}", ip))
                    seen_ips.add(ip)
        elif kubectl_parsed is not None:
            # Extract InternalIP from each node item in the kubectl response
            items: list = kubectl_parsed.get("items", [])
            for item in items:
                addresses: list = item.get("status", {}).get("addresses", [])
                internal_ip: str | None = None
                for addr in addresses:
                    if addr.get("type") == "InternalIP":
                        internal_ip = addr.get("address")
                        break
                if internal_ip and internal_ip not in seen_ips:
                    hosts.append(("kube", f"kubenode-{internal_ip}", internal_ip))
                    seen_ips.add(internal_ip)

        # Data nodes second skip IPs already covered by kube nodes
        if self._config.nodes.data_nodes:
            for ip in self._config.nodes.data_nodes:
                if ip not in seen_ips:
                    hosts.append(("data", f"datanode-{ip}", ip))
                    seen_ips.add(ip)
        else:
            db_ips: list[str] = [
                db.cassandra,
                db.elasticsearch,
                db.minio,
                db.postgresql,
                db.rabbitmq,
            ]
            for ip in db_ips:
                if ip and ip not in seen_ips:
                    hosts.append(("data", f"datanode-{ip}", ip))
                    seen_ips.add(ip)

        # ── SSH-check each node ─────────────────────────────────────────────
        results: list[PreflightResult] = []

        for _role, node_label, ip in hosts:
            # Determine routing and build the detail string shown in output
            needs_jump: bool = (
                self._config.gathered_from != 'admin-host'
                and bool(db.ssh_key)
            )

            if db.ssh_key:
                detail: str = f"{db.ssh_user}@{ip}:{db.ssh_port}"
            else:
                detail = (
                    f"{self._config.admin_host.user}@{ip}:"
                    f"{self._config.admin_host.ssh_port}"
                )

            if needs_jump and not admin_ssh_ok:
                results.append(PreflightResult(
                    name        = f"SSH - {node_label}",
                    detail      = detail,
                    success     = False,
                    message     = "",
                    skipped     = True,
                    skip_reason = "admin host SSH failed",
                ))
                continue

            try:
                cmd_result: CommandResult
                if self._config.gathered_from == 'admin-host':
                    if db.ssh_key:
                        cmd_result = self._ssh.db_to(ip).run("echo preflight_ok")
                    else:
                        cmd_result = self._ssh.to(ip).run("echo preflight_ok")
                elif db.ssh_key:
                    cmd_result = self._ssh.via(
                        self._config.admin_host.ip
                    ).to(ip).run("echo preflight_ok")
                else:
                    cmd_result = self._ssh.to(ip).run("echo preflight_ok")

                if cmd_result.exit_code == 0 and "preflight_ok" in cmd_result.stdout:
                    results.append(PreflightResult(
                        name    = f"SSH - {node_label}",
                        detail  = detail,
                        success = True,
                        message = "connected",
                    ))
                else:
                    error_text: str = (
                        cmd_result.stderr.strip().splitlines()[0]
                        if cmd_result.stderr.strip()
                        else f"unexpected output (exit {cmd_result.exit_code})"
                    )
                    results.append(PreflightResult(
                        name    = f"SSH - {node_label}",
                        detail  = detail,
                        success = False,
                        message = error_text,
                    ))

            except Exception as exc:
                results.append(PreflightResult(
                    name    = f"SSH - {node_label}",
                    detail  = detail,
                    success = False,
                    message = str(exc),
                ))

        return results

    # ── Output helpers ───────────────────────────────────────────────────────

    def _print_result(self, result: PreflightResult) -> None:
        """Print a single check result line to the terminal.

        Format:
          ✓ SSH admin host (deploy@10.0.0.1:22) connected
          ✗ SSH admin host (deploy@10.0.0.1:22) Connection refused
          – SSH cassandra VM (wire@192.168.1.20:22) skipped (admin host SSH failed)

        Args:
            result: The check result to display.
        """
        # Compose the label: name + detail in parens
        label_prefix: str
        if result.detail:
            label_prefix = f"{result.name} ({result.detail})"
        else:
            label_prefix = result.name

        if result.skipped:
            self._terminal.check_skip(f"{label_prefix} - {result.skip_reason}")
        elif result.success:
            self._terminal.check_pass(f"{label_prefix} - {result.message}")
        else:
            self._terminal.check_fail(f"{label_prefix} - {result.message}")
