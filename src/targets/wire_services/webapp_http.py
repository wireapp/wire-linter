"""Checks if the Wire Webapp is accessible via HTTP.

This is what end users actually load in their browser. A failing
webapp HTTP check means users cannot access Wire at all.

Topology-aware: tries the standard URL first (webapp.<domain>:443), then
falls back to the kube node NodePort if the standard URL is unreachable.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


class WebappHttp(BaseTarget):
    """Checks if the Wire Webapp responds to HTTP requests.

    Curls the webapp URL from the admin host and checks for
    a 2xx or 3xx response code.
    """

    # Uses SSH to admin host for curl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Webapp HTTP accessibility"

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
        """Check if the webapp responds with a success or redirect code (2xx/3xx).

        Tries the standard URL first (https://webapp.<domain>/).
        If that fails with connection error (HTTP 0), falls back to curling
        a kube node on the ingress NodePort with the correct Host header.

        Returns:
            True if webapp responds with 2xx/3xx, False otherwise.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        url: str = f"https://webapp.{domain}/"

        self.terminal.step(f"Checking webapp at {url}...")

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

        fallback_url: str = f"https://{kube_ip}:{nodeport}/"
        fallback_result = self.run_ssh(
            self.config.admin_host.ip,
            f"curl -sk -o /dev/null -w '%{{http_code}}' --max-time 10 "
            f"-H 'Host: webapp.{domain}' '{fallback_url}' 2>/dev/null",
        )

        try:
            return int(fallback_result.stdout.strip())
        except ValueError:
            return 0
