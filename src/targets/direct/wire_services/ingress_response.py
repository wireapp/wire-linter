"""Checks if the Nginx ingress controller responds to direct HTTP requests.

If the ingress is broken, all API traffic fails even if the backend
pods are healthy. Tests via the nginz-https status endpoint.

This is the direct-HTTP variant of src/targets/wire_services/ingress_response.py
for use when the linter can reach the Wire domain without SSH tunneling.

Topology-aware: tries the standard URL first (domain:443), then falls back
to the kube node NodePort if the standard URL is unreachable (common in
offline deployments where the admin host doesn't proxy port 443).
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.http_client import HttpResult, http_get
from src.lib.shell_safety import validate_domain_for_shell


class IngressResponse(BaseTarget):
    """Checks if the ingress controller responds to direct HTTP requests.

    Makes HTTP requests directly from the linter machine instead of
    SSH+curl through an admin host.
    """

    # Direct HTTP to the Wire domain — only works from outside the cluster
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Ingress controller response test (direct HTTP)"

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
        If that fails with connection error (status_code 0), falls back to
        hitting a kube node on the ingress NodePort with the correct Host header.

        Returns:
            True if the ingress routes traffic (any non-server-error response),
            False if unreachable or returning 5xx. Note: 4xx responses still mean
            the ingress is alive and routing — the error comes from the backend,
            not the ingress itself. This differs from the webapp check which
            requires 2xx/3xx to confirm content is actually served.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        url: str = f"https://nginz-https.{domain}/status"

        self.terminal.step(f"Checking ingress at {url}...")

        result: HttpResult = self.http_get(url, timeout=10)
        code: int = result.status_code

        # Connection failed -- try the NodePort fallback before giving up
        if code == 0:
            fallback_code: int = self._try_nodeport_fallback(domain)
            if fallback_code > 0:
                code = fallback_code

        # Any non-5xx HTTP response means the ingress is alive and routing
        # traffic. 4xx codes indicate a backend issue, not an ingress failure.
        responsive: bool = code > 0 and code < 500

        if responsive:
            self._health_info = f"Ingress routes traffic (HTTP {code})"
        elif code == 0:
            self._health_info = "Ingress unreachable (connection failed)"
        else:
            self._health_info = f"Ingress returned server error (HTTP {code})"

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

        # Call the standalone http_get with Host header since
        # BaseTarget.http_get doesn't support custom headers
        fallback_url: str = f"https://{kube_ip}:{nodeport}/status"
        fallback_result: HttpResult = http_get(
            fallback_url,
            timeout=10,
            headers={"Host": f"nginz-https.{domain}"},
        )

        # Track the fallback output the same way BaseTarget.http_get does
        # Ensure non-empty output on failure so raw_output shows what was attempted
        tracked_output: str = (
            fallback_result.body if fallback_result.success
            else (fallback_result.error or f"Connection to {fallback_url} failed")
        )
        self.terminal.command_result(tracked_output)
        self._track_output(f"GET {fallback_url}", tracked_output)

        return fallback_result.status_code
