"""Checks Wire service /i/status endpoints.

Each service exposes /i/status for internal health checks. We curl them
through the ingress to verify they're reachable.

Topology-aware: tries the standard URL first (nginz-https.<domain>:443),
then falls back to the kube node NodePort if the standard URL is
unreachable (common in offline deployments).
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
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
    """Checks Wire service /i/status endpoints."""

    # Uses SSH to admin host for curl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        return "Wire service /i/status endpoint responses"

    @property
    def explanation(self) -> str:
        return (
            "If a service doesn't respond on /i/status, it's either down or "
            "the ingress can't reach it."
        )

    def collect(self) -> str:
        """Check /i/status endpoints for all core Wire services.

        Tries the standard URL first for each service. If the standard URL
        fails (HTTP 0 / connection refused), falls back to the NodePort
        for that individual service. NodePort discovery results are cached
        so we only look them up once.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        responding: list[str] = []
        responding_with_errors: list[str] = []
        erroring: list[str] = []
        not_responding: list[str] = []

        # Cached NodePort discovery results — resolved once, reused per service
        nodeport: int = 0
        kube_ip: str = ''
        nodeport_discovered: bool = False

        for svc in _STATUS_SERVICES:
            self.terminal.step(f"Checking {svc['name']} status endpoint...")

            # Always try the standard URL first for every service
            url: str = f"https://nginz-https.{domain}{svc['path']}"
            result = self.run_ssh(
                self.config.admin_host.ip,
                f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 "
                f"'{url}' 2>/dev/null",
            )
            status_code: str = result.stdout.strip()

            # If the standard URL failed, try the NodePort fallback for this service
            if status_code == '000' or status_code == '':
                # Discover NodePort once, cache for subsequent services
                if not nodeport_discovered:
                    nodeport = self.discover_ingress_https_nodeport()
                    kube_ip = self.get_first_kube_node_ip()
                    nodeport_discovered = True

                # Emit per-service message so operators know each service
                # that fell back to NodePort, not just the first one
                if nodeport and kube_ip:
                    self.terminal.step(
                        f"Standard port 443 unreachable for "
                        f"{svc['name']}, falling back to "
                        f"NodePort {nodeport} on {kube_ip}"
                    )

                if nodeport and kube_ip:
                    fallback_url: str = (
                        f"https://{kube_ip}:{nodeport}{svc['path']}"
                    )
                    fallback_result = self.run_ssh(
                        self.config.admin_host.ip,
                        f"curl -sk -o /dev/null -w '%{{http_code}}' "
                        f"--max-time 5 "
                        f"-H 'Host: nginz-https.{domain}' "
                        f"'{fallback_url}' 2>/dev/null",
                    )
                    status_code = fallback_result.stdout.strip()

            # Classify the response: 2xx/3xx = healthy, 4xx = reachable but
            # returning errors (auth, not-found, etc.), 5xx or 0 = down/unreachable.
            try:
                code: int = int(status_code)
            except ValueError:
                code = 0

            if 200 <= code < 400:
                responding.append(svc["name"])
            elif 400 <= code < 500:
                # 401/403 are common when the ingress requires auth on /i/status,
                # 404 may indicate a broken route. Either way the service is
                # reachable but not confirmed healthy — track separately.
                responding_with_errors.append(f"{svc['name']} (HTTP {code})")
            elif code >= 500:
                # 5xx means the service is reachable but returning a server error
                # (e.g. 503 during rolling upgrade, 502 from overloaded ingress)
                erroring.append(f"{svc['name']} ({status_code})")
            else:
                # code == 0: connection refused, timeout, or unparseable response
                not_responding.append(f"{svc['name']} ({status_code})")

        # Only raise when every service returned code==0 (connection refused/timeout),
        # meaning none were reachable at all. Services returning 5xx are reachable
        # (network-wise) and should produce a health summary, not an exception.
        if not responding and not responding_with_errors and not erroring:
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

        if erroring:
            parts.append(
                f"erroring: {', '.join(erroring)}"
            )

        if not_responding:
            parts.append(
                f"not responding: {', '.join(not_responding)}"
            )

        self._health_info = ", ".join(parts)

        return f"{len(responding)}/{total} healthy"
