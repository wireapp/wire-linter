"""Checks that Wire's essential ports are actually reachable.

Wire needs ports 443 (HTTPS), 80 (HTTP redirect), and 3478 (TURN)
to work properly. If these ports are blocked, features silently fail
without warning the user.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


# The ports Wire actually needs to work
_REQUIRED_PORTS: list[dict[str, str | int]] = [
    {"port": 443, "proto": "tcp", "service": "HTTPS"},
    {"port": 80, "proto": "tcp", "service": "HTTP"},
    {"port": 3478, "proto": "tcp", "service": "TURN/TCP"},
]


class PortReachability(BaseTarget):
    """Checks if we can reach Wire's critical ports.

    We test from the admin host using netcat to see if TCP connections
    to the required ports on the Wire domain actually work.
    """

    # This only makes sense when you're running from somewhere with internet access,
    # since we're testing if external clients can reach Wire.
    requires_external_access: bool = True

    # Uses SSH to admin host for port checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Short summary of what we're checking."""
        return "Essential ports reachable (443, 80, 3478)"

    @property
    def explanation(self) -> str:
        """Why we care about this and what it means if it fails."""
        return (
            "Wire needs ports 443 (HTTPS), 80 (HTTP redirect), and 3478 (TURN). "
            "If they're blocked, users get silent failures when trying to log in, make calls, or share media."
        )

    def collect(self) -> str:
        """Check if we can reach all the important ports.

        Returns:
            A summary like « 3/3 reachable ».
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        reachable: list[str] = []
        unreachable: list[str] = []

        for port_info in _REQUIRED_PORTS:
            port: int = int(port_info["port"])
            service: str = str(port_info["service"])

            self.terminal.step(f"Testing port {port} ({service})...")

            # nc -z does a quick TCP port check with a 3 second timeout
            result = self.run_ssh(
                self.config.admin_host.ip,
                f"nc -z -w 3 {domain} {port} 2>&1 && echo OPEN || echo CLOSED",
            )

            output: str = result.stdout.strip()

            if "OPEN" in output or "succeeded" in output.lower():
                reachable.append(f"{port}/{service}")
            else:
                unreachable.append(f"{port}/{service}")

        total: int = len(_REQUIRED_PORTS)

        if not unreachable:
            self._health_info = f"All {total} essential ports reachable"
        else:
            self._health_info = (
                f"{len(reachable)}/{total} reachable, "
                f"unreachable: {', '.join(unreachable)}"
            )

        return f"{len(reachable)}/{total} reachable"
