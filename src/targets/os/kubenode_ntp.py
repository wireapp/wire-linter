"""Checks NTP synchronization on each kubenode via SSH.

If the clock drifts on kubenodes, certs fail validation and logs get messed up
timestamps across services. (This is different from the admin host NTP check.)
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.per_host_target import PerHostTarget


class KubenodeNtp(PerHostTarget):
    """Checks NTP synchronization on each Kubernetes node.

    Find kubenodes via kubectl, then SSH into each and run timedatectl
    to see if the clock is synced.
    """

    @property
    def description(self) -> str:
        """What this check is looking for."""
        return "NTP synchronization"

    @property
    def explanation(self) -> str:
        """Why we care clock drift breaks certs and timestamp logs."""
        return (
            "Clock drift on kubenodes breaks certificate validation and messes up "
            "log timestamps. Good when timedatectl says synchronized."
        )

    @property
    def unit(self) -> str:
        """No unit just yes/no for synced or not."""
        return ""

    def get_hosts(self) -> list[dict[str, str]]:
        """Get the list of kubenodes to check.

        If you configured kube_nodes explicitly, use those. Otherwise,
        ask kubectl for the nodes. We name them kubenode-{ip} to match
        how vm_hosts does discovery.

        Returns:
            List of host dicts with 'name' and 'ip' keys.
        """
        # Use explicit config if it's there, otherwise ask kubectl
        if self.config.nodes.kube_nodes:
            return [
                {"name": f"kubenode-{ip}", "ip": ip}
                for ip in self.config.nodes.kube_nodes
            ]

        # Query kubectl for nodes if not in config
        _cmd_result, data = self.run_kubectl("nodes")

        if data is None:
            return []

        hosts: list[dict[str, str]] = []
        items: list[dict[str, Any]] = data.get("items", [])

        for item in items:
            addresses: list[dict[str, str]] = item.get("status", {}).get("addresses", [])

            for addr in addresses:
                if addr.get("type") == "InternalIP":
                    ip: str | None = addr.get("address")
                    if ip:
                        # Match the vm_hosts naming pattern
                        hosts.append({"name": f"kubenode-{ip}", "ip": ip})
                    break

        return hosts

    def collect_for_host(self, host: dict[str, str]) -> bool:
        """SSH into the kubenode and check if NTP is synced.

        Args:
            host: Dict with 'name' and 'ip' keys identifying the kubenode.

        Returns:
            True if NTP is synchronized, False otherwise.
        """
        self.terminal.step(f"Checking NTP sync on {host['name']}...")

        # timedatectl show gives us key=value format which is easier to parse
        result = self.run_ssh(host["ip"], "timedatectl show 2>/dev/null || timedatectl status")

        output: str = result.stdout.strip()

        # Look for the machine-readable format first (NTPSynchronized=yes)
        for line in output.split("\n"):
            if line.startswith("NTPSynchronized="):
                value: str = line.split("=", 1)[1].strip()
                synced: bool = value.lower() == "yes"
                self._health_info = "Clock synchronized" if synced else "Clock NOT synchronized"
                return synced

        # If that doesn't work, search for "synchronized" in the output
        for line in output.split("\n"):
            if "synchronized" in line.lower():
                synced = line.split(":", 1)[-1].strip().lower() == "yes"
                self._health_info = "Clock synchronized" if synced else "Clock NOT synchronized"
                return synced

        self._health_info = "Could not determine NTP sync status"
        return False

    def description_for_host(self, host: dict[str, str]) -> str:
        """Get a label for this host in the results.

        Args:
            host: Dict with 'name' and 'ip' keys.

        Returns:
            A string describing which host we checked.
        """
        return f"NTP synchronization on {host['name']} ({host['ip']})"
