"""Checks the net.ipv4.ip_unprivileged_port_start kernel parameter on each kubenode.

Wire needs ports 443 and 80 for ingress-nginx and coturn. If ip_unprivileged_port_start
is set above 443, rootless containers can't bind to those ports and Wire breaks (JCT-34).
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.per_host_target import PerHostTarget


# Wire needs this port and below (ip_unprivileged_port_start must not exceed it)
_WIRE_MIN_PORT: int = 443


class UnprivilegedPortStart(PerHostTarget):
    """Checks net.ipv4.ip_unprivileged_port_start on each kubenode.

    Logs into each node via SSH and reads the sysctl value. If it's above 443,
    rootless containers can't reach those ports and Wire's ingress breaks.
    """

    @property
    def description(self) -> str:
        """What we're checking on the node."""
        return "net.ipv4.ip_unprivileged_port_start kernel parameter"

    @property
    def explanation(self) -> str:
        """Why this matters and what's good vs bad."""
        return (
            "ingress-nginx and coturn need ports 443 and 80. If ip_unprivileged_port_start "
            "is above 443, they can't bind and Wire breaks. Keep it at 443 or lower (JCT-34)."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty, it's just a port number)."""
        return ""

    def get_hosts(self) -> list[dict[str, str]]:
        """Get all the kubenodes to check.

        Returns:
            List of dicts with 'name' and 'ip' for each node.
        """
        _cmd_result, data = self.run_kubectl("nodes")

        if data is None:
            return []

        hosts: list[dict[str, str]] = []
        items: list[dict[str, Any]] = data.get("items", [])

        for item in items:
            node_name: str = item["metadata"]["name"]
            addresses: list[dict[str, str]] = item.get("status", {}).get("addresses", [])

            for addr in addresses:
                if addr.get("type") == "InternalIP":
                    ip: str | None = addr.get("address")
                    if ip:
                        hosts.append({"name": node_name, "ip": ip})
                    break

        return hosts

    def collect_for_host(self, host: dict[str, str]) -> int:
        """SSH into the node and grab the sysctl value.

        Args:
            host: Dict with 'name' and 'ip' for the node.

        Returns:
            The kernel parameter value. Should be <= 443.

        Raises:
            RuntimeError: If sysctl can't be read.
        """
        self.terminal.step(
            f"Reading ip_unprivileged_port_start on {host['name']}..."
        )

        result = self.run_ssh(
            host["ip"],
            "sysctl -n net.ipv4.ip_unprivileged_port_start 2>/dev/null || echo 'not_found'",
        )

        output: str = result.stdout.strip()

        if not output or output == "not_found":
            raise RuntimeError(
                f"Could not read net.ipv4.ip_unprivileged_port_start on {host['name']}"
            )

        try:
            value: int = int(output)
        except ValueError:
            raise RuntimeError(
                f"Unexpected sysctl output on {host['name']}: {output!r}"
            )

        if value <= _WIRE_MIN_PORT:
            self._health_info = (
                f"ip_unprivileged_port_start={value} "
                f"(rootless containers can bind to port {_WIRE_MIN_PORT})"
            )
        else:
            self._health_info = (
                f"ip_unprivileged_port_start={value} "
                f"(PROBLEM: must be <= {_WIRE_MIN_PORT} for Wire ingress to bind)"
            )

        return value

    def description_for_host(self, host: dict[str, str]) -> str:
        """Label for this node in the results display.

        Args:
            host: Dict with 'name' and 'ip' keys.

        Returns:
            A label showing which node and IP this value came from.
        """
        return (
            f"net.ipv4.ip_unprivileged_port_start on {host['name']} ({host['ip']})"
        )
