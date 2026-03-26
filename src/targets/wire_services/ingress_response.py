"""Checks if the Nginx ingress controller responds to requests.

If the ingress is broken, all API traffic fails even if the backend
pods are healthy. Tests via the nginz-https status endpoint.

Topology-aware: tries the standard URL first (domain:443), then falls back
to the kube node NodePort if the standard URL is unreachable (common in
offline deployments where the admin host doesn't proxy port 443).
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


class IngressResponse(BaseTarget):
    """Checks if the ingress controller responds.

    Curls the nginz-https status endpoint from the admin host
    to verify the ingress controller is forwarding traffic.
    """

    # Uses SSH to admin host for curl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Ingress controller response test"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "The ingress controller routes all external API traffic. If it doesn't "
            "respond, every Wire client loses connectivity even if backend services "
            "are healthy."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty for boolean results)."""
        return ""

    def collect(self) -> bool:
        """Check if the ingress controller responds.

        Tries the standard URL first (https://nginz-https.<domain>/status).
        If that fails with connection error (HTTP 0), falls back to curling
        a kube node on the ingress NodePort with the correct Host header.

        Returns:
            True if ingress responds with any code < 500 (2xx/3xx/4xx all indicate a live ingress), False otherwise.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        url: str = f"https://nginz-https.{domain}/status"

        self.terminal.step(f"Checking ingress at {url}...")

        result = self.run_ssh(
            self.config.admin_host.ip,
            f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 '{url}' 2>/dev/null",
        )

        status_code: str = result.stdout.strip()

        try:
            code: int = int(status_code)
        except ValueError:
            code = 0

        # Connection failed — try the NodePort fallback before giving up
        if code == 0:
            fallback_code: int = self._try_nodeport_fallback(domain)
            if fallback_code > 0:
                code = fallback_code

        # 4xx responses still mean the ingress is alive and routing (backend is rejecting, not ingress failing)
        responsive: bool = code > 0 and code < 500

        if responsive:
            self._health_info = f"Ingress responding (HTTP {code})"
        else:
            self._health_info = f"Ingress returned HTTP {code}"

        return responsive

    def _try_nodeport_fallback(self, domain: str) -> int:
        """Try reaching the ingress via kube node NodePort.

        In offline/private deployments, the domain might resolve to the admin
        host which doesn't listen on 443. The actual ingress runs as a
        Kubernetes NodePort on the kube nodes.

        Args:
            domain: Cluster domain for the Host header.

        Returns:
            HTTP status code from the NodePort attempt, or 0 if fallback unavailable.
        """
        nodeport: int = self.discover_ingress_https_nodeport()
        kube_ip: str = self.get_first_kube_node_ip()

        if not nodeport or not kube_ip:
            return 0

        self.terminal.step(
            f"Standard port 443 unreachable, trying NodePort {nodeport} "
            f"on kube node {kube_ip}..."
        )

        fallback_url: str = f"https://{kube_ip}:{nodeport}/status"
        fallback_result = self.run_ssh(
            self.config.admin_host.ip,
            f"curl -sk -o /dev/null -w '%{{http_code}}' --max-time 10 "
            f"-H 'Host: nginz-https.{domain}' '{fallback_url}' 2>/dev/null",
        )

        try:
            return int(fallback_result.stdout.strip())
        except ValueError:
            return 0
