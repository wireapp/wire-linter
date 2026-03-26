"""Checks Wire service /i/status endpoints via direct HTTP.

Each service exposes /i/status for internal health checks. We hit them
through the ingress directly from the linter machine (no SSH needed).

This is the direct-HTTP variant of src/targets/wire_services/status_endpoints.py
for use when the linter can reach the Wire domain without SSH tunneling.

Topology-aware: tries the standard URL first (nginz-https.<domain>:443),
then falls back to the kube node NodePort if the standard URL is
unreachable (common in offline deployments).
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.http_client import HttpResult, http_get
from src.lib.shell_safety import validate_domain_for_shell


# Services with /i/status endpoints we can reach via the ingress.
# Each path uses the service-specific ingress route so we actually
# hit a different backend for each entry.
_STATUS_SERVICES: list[dict[str, str]] = [
    {"name": "brig", "path": "/brig/i/status"},
    {"name": "galley", "path": "/galley/i/status"},
    {"name": "gundeck", "path": "/gundeck/i/status"},
    {"name": "cargohold", "path": "/cargohold/i/status"},
    {"name": "cannon", "path": "/cannon/i/status"},
    {"name": "spar", "path": "/spar/i/status"},
]


class StatusEndpoints(BaseTarget):
    """Checks Wire service /i/status endpoints via direct HTTP.

    Makes HTTP requests directly from the linter machine instead of
    SSH+curl through an admin host.
    """

    # Direct HTTP to the Wire domain — only works from outside the cluster
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Wire service /i/status endpoint responses (direct HTTP)"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "If a service doesn't respond on /i/status, it's either down or "
            "the ingress can't reach it."
        )

    def collect(self) -> str:
        """Check /i/status endpoints for all core Wire services.

        Tries the standard URL first. If the first service gets a connection
        error (status_code 0), switches to the NodePort fallback for all
        remaining services too.

        Returns:
            Summary string like "6/6 responding".

        Raises:
            RuntimeError: If no services respond at all.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        responding: list[str] = []
        responding_with_errors: list[str] = []
        not_responding: list[str] = []

        # Track whether the standard port works so we can skip straight to
        # NodePort for subsequent services if the first one fails to connect
        use_nodeport: bool = False
        nodeport: int = 0
        kube_ip: str = ''

        for svc in _STATUS_SERVICES:
            self.terminal.step(f"Checking {svc['name']} status endpoint...")

            code: int = 0

            # Try standard URL first (unless we already know it doesn't work)
            if not use_nodeport:
                url: str = f"https://nginz-https.{domain}{svc['path']}"
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
                fallback_url: str = (
                    f"https://{kube_ip}:{nodeport}{svc['path']}"
                )
                self.terminal.step(f"HTTP GET {fallback_url} (NodePort fallback)")

                fallback_result: HttpResult = http_get(
                    fallback_url,
                    timeout=5,
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

                code = fallback_result.status_code

            # Classify the response: 2xx/3xx = healthy, 4xx = reachable but
            # returning errors (auth, not-found, etc.), 5xx or 0 = down/unreachable.
            if 200 <= code < 400:
                responding.append(svc["name"])
            elif 400 <= code < 500:
                # 401/403 are common when the ingress requires auth on /i/status,
                # 404 may indicate a broken route. Either way the service is
                # reachable but not confirmed healthy — track separately.
                responding_with_errors.append(f"{svc['name']} (HTTP {code})")
            else:
                not_responding.append(f"{svc['name']} ({code})")

        if not responding and not responding_with_errors:
            details: str = ", ".join(not_responding)
            raise RuntimeError(
                f"Could not reach any Wire service status endpoints: {details}"
            )

        total: int = len(_STATUS_SERVICES)

        # Build a health summary that distinguishes truly healthy (2xx/3xx)
        # from reachable-but-erroring (4xx) and unreachable/down (5xx/0)
        parts: list[str] = []
        parts.append(f"{len(responding)}/{total} healthy")

        if responding_with_errors:
            parts.append(
                f"{len(responding_with_errors)} responding with errors: "
                f"{', '.join(responding_with_errors)}"
            )

        if not_responding:
            parts.append(
                f"not responding: {', '.join(not_responding)}"
            )

        self._health_info = ", ".join(parts)

        return f"{len(responding)}/{total} healthy"
