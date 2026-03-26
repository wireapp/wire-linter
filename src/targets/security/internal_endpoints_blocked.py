"""Checks that internal /i/ endpoints are not reachable from outside.

Internal endpoints (/i/users, /i/teams, /i/legalhold, etc.) shouldn't
be reachable externally. Only nginz should forward authenticated requests
internally.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


class InternalEndpointsBlocked(BaseTarget):
    """Checks that /i/ endpoints are not externally accessible.

    Curls internal endpoints from the admin host (simulating external access
    via the public domain) to verify they're blocked.
    """

    # Skip this check from within the admin-host shell runner would be on
    # the internal network making results ambiguous (can't tell internal vs
    # external reachability).
    #
    # When running externally, collect() SSHes to the admin host and runs curl
    # there. This works because admin host resolves nginz-https.<domain> via
    # public DNS/external load-balancer, not cluster-internal IP, so it sees
    # the same firewall and LB rules as a real external client. If that ever
    # changes (internal DNS override, etc) we'd need to run curl from a truly
    # external host instead.
    requires_external_access: bool = True

    # Uses SSH to admin host for curl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Internal /i/ endpoints not reachable externally"

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

        Curl runs on the admin host via SSH intentional because admin host
        uses public DNS for nginz-https.<domain>, so it hits the external
        load-balancer and sees the same firewall rules as a real external client.
        This is a valid signal for external reachability, not an internal bypass.

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

        for path in test_paths:
            url: str = f"https://nginz-https.{domain}{path}"
            self.terminal.step(f"Testing external access to {path}...")

            result = self.run_ssh(
                self.config.admin_host.ip,
                f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 '{url}' 2>/dev/null",
            )

            status_code_str: str = result.stdout.strip()

            # Any non-error response (1xx, 2xx, 3xx) means the endpoint is
            # exposed. 4xx/5xx or connection failures (code 0/empty) are fine.
            try:
                code: int = int(status_code_str)
            except ValueError:
                code = 0

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
