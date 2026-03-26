"""Checks that internal /i/ endpoints are not reachable from outside via direct HTTP.

Internal endpoints (/i/users, /i/status, /i/teams, etc.) shouldn't be reachable externally.
Only nginz should forward authenticated requests internally.

This is the direct-HTTP variant of src/targets/security/internal_endpoints_blocked.py
for use when the linter can reach the Wire domain without SSH tunneling (e.g.
in only_through_kubernetes mode).

Topology-aware: tries the standard URL first (nginz-https.<domain>:443), then
falls back to the kube node NodePort if the standard URL is unreachable (common
in offline deployments where the admin host doesn't proxy port 443).
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.http_client import HttpResult, http_get
from src.lib.shell_safety import validate_domain_for_shell


class InternalEndpointsBlocked(BaseTarget):
    """Checks that /i/ endpoints are not externally accessible via direct HTTP.

    Makes HTTP requests directly from the linter machine instead of
    SSH+curl through an admin host.
    """

    # This target tests external reachability -- when running from the
    # admin host the request comes from inside the network, making results
    # ambiguous (can't distinguish internal vs external reachability).
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Internal /i/ endpoints not reachable externally (direct HTTP)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Internal /i/ endpoints give direct access to user data and admin operations. "
            "They should only be reachable via internal service mesh. Good when external "
            "requests to /i/ paths return 4xx/5xx error responses (not 1xx/2xx/3xx)."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check that /i/ endpoints return error responses externally.

        Makes direct HTTP requests from the linter machine to the public
        domain. Tries the standard URL first, falls back to kube node
        NodePort if unreachable.

        Returns:
            True if internal endpoints are blocked, False if accessible.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)

        # Test representative internal endpoints across different services
        # to catch path-specific ACL misconfigurations in nginz
        test_paths: list[str] = [
            "/i/status",
            "/i/users",
            "/i/teams",
            "/i/connections",
            "/i/clients",
            "/i/provider",
            "/i/legalhold",
            "/i/billing",
        ]

        accessible: list[str] = []

        # Track whether the standard port works so we can skip straight to
        # NodePort for subsequent paths if the first one fails to connect
        use_nodeport: bool = False
        nodeport: int = 0
        kube_ip: str = ''

        for path in test_paths:
            self.terminal.step(f"Testing external access to {path}...")
            code: int = 0

            # Try standard URL first (unless we already know it doesn't work)
            if not use_nodeport:
                url: str = f"https://nginz-https.{domain}{path}"
                result: HttpResult = self.http_get(url, timeout=5)
                code = result.status_code

                # If connection failed, discover NodePort for fallback
                if code == 0:
                    nodeport = self.discover_ingress_https_nodeport()
                    kube_ip = self.get_first_kube_node_ip()
                    if nodeport and kube_ip:
                        use_nodeport = True
                        self.terminal.step(
                            f"Standard port 443 unreachable, switching to "
                            f"NodePort {nodeport} on {kube_ip}"
                        )

            # NodePort fallback: call the standalone http_get with Host header
            # since BaseTarget.http_get doesn't support custom headers
            if use_nodeport:
                fallback_url: str = f"https://{kube_ip}:{nodeport}{path}"
                self.terminal.step(f"HTTP GET {fallback_url} (NodePort fallback)")

                fallback_result: HttpResult = http_get(
                    fallback_url,
                    timeout=5,
                    headers={"Host": f"nginz-https.{domain}"},
                )

                # Track the fallback output the same way BaseTarget.http_get does
                tracked_output: str = (
                    fallback_result.body if fallback_result.success
                    else (fallback_result.error or "")
                )
                self.terminal.command_result(tracked_output)
                self._track_output(f"GET {fallback_url}", tracked_output)

                code = fallback_result.status_code

            # Any non-error response (1xx, 2xx, 3xx) means the endpoint is
            # exposed. 4xx/5xx or connection failures (code 0/empty) are fine.
            if 0 < code < 400:
                accessible.append(f"{path} (HTTP {code})")

        all_blocked: bool = len(accessible) == 0

        if all_blocked:
            self._health_info = "Internal /i/ endpoints blocked"
        else:
            self._health_info = (
                f"SECURITY: Internal endpoints accessible: {', '.join(accessible)}"
            )

        return all_blocked
