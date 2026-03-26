"""Checks if the Wire Webapp is accessible via direct HTTP.

This is what end users actually load in their browser. A failing
webapp HTTP check means users cannot access Wire at all.

This is the direct-HTTP variant of src/targets/wire_services/webapp_http.py
for use when the linter can reach the Wire domain without SSH tunneling.

Topology-aware: tries the standard URL first (webapp.<domain>:443), then
falls back to the kube node NodePort if the standard URL is unreachable.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.http_client import HttpResult, http_get
from src.lib.shell_safety import validate_domain_for_shell


class WebappHttp(BaseTarget):
    """Checks if the Wire Webapp responds to direct HTTP requests.

    Makes HTTP requests directly from the linter machine instead of
    SSH+curl through an admin host.
    """

    # Direct HTTP to the Wire domain — only works from outside the cluster
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Webapp HTTP accessibility (direct HTTP)"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "The webapp URL is what end users load in their browser. If it's broken, "
            "nobody can use Wire."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty, since this is a pass/fail check)."""
        return ""

    def collect(self) -> bool:
        """Check if the webapp responds with an HTTP success code.

        Tries the standard URL first (https://webapp.<domain>/).
        If that fails with connection error (status_code 0), falls back to
        hitting a kube node on the ingress NodePort with the correct Host header.

        Returns:
            True if webapp responds with 2xx/3xx, False otherwise.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        url: str = f"https://webapp.{domain}/"

        self.terminal.step(f"Checking webapp at {url}...")

        result: HttpResult = self.http_get(url, timeout=10)
        code: int = result.status_code

        # Connection failed -- try the NodePort fallback before giving up
        if code == 0:
            fallback_code: int = self._try_nodeport_fallback(domain)
            if fallback_code > 0:
                code = fallback_code

        accessible: bool = 200 <= code < 400

        if accessible:
            self._health_info = f"Webapp accessible (HTTP {code})"
        elif code == 0:
            self._health_info = "Webapp unreachable (connection failed)"
        else:
            self._health_info = f"Webapp returned HTTP {code}"

        return accessible

    def _try_nodeport_fallback(self, domain: str) -> int:
        """Try reaching the webapp via kube node NodePort.

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
        fallback_url: str = f"https://{kube_ip}:{nodeport}/"
        fallback_result: HttpResult = http_get(
            fallback_url,
            timeout=10,
            headers={"Host": f"webapp.{domain}"},
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
