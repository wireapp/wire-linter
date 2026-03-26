"""Checks total root filesystem size in GiB on each VM host.

Connects to each VM via SSH and runs df to get the root filesystem total.
Together with disk_usage (percentage), the UI can compute absolute used/free
disk space.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


class VmDiskTotal(PerHostTarget):
    """Checks total disk size on each VM.

    Discovers VM hosts via kubectl node labels, then SSHes into each one
    to read the root partition total from df output and normalize to GiB.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Disk total"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Records total disk size per VM. Combined with disk usage %, "
            "lets you compute absolute free space and plan capacity."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the collected value."""
        return "Gi"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return the list of VM hosts to check.

        Returns:
            List of host dicts with 'name' and 'ip' keys.
        """
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> float:
        """SSH into host and parse total root filesystem size from df.

        Uses «df -BM /» to get the size in mebibytes (MiB), then converts to GiB
        for consistency with the memory targets. The «-BM» flag avoids
        human-readable suffixes (G, T) that would need extra parsing.

        Args:
            host: Dict with 'name' and 'ip' keys identifying the target VM.

        Returns:
            Float GiB of total root filesystem rounded to one decimal place.

        Raises:
            RuntimeError: If df output is missing or has fewer fields than expected.
        """
        self.terminal.step(f"Checking total disk on {host['name']}...")

        # df -BM forces output in mebibytes (e.g. «98765M»), avoiding ambiguous suffixes
        result = self.run_ssh(host["ip"], "df -BM / | tail -1")

        fields: list[str] = result.stdout.strip().split()

        # df produces: Filesystem 1M-blocks Used Available Use% Mounted-on
        if len(fields) < 2:
            raise RuntimeError(
                f"Unexpected df output on {host['name']}: expected >= 2 fields, got {len(fields)}"
            )

        # Field index 1 is the «Size» column in MiB strip trailing «M» suffix
        size_str: str = re.sub(r"[^0-9]", "", fields[1])

        if not size_str:
            raise RuntimeError(
                f"Could not parse disk size from df output on {host['name']}: {fields[1]}"
            )

        total_mib: int = int(size_str)

        # Convert MiB to GiB
        total_gi: float = round(total_mib / 1024, 1)

        return total_gi

    def description_for_host(self, host: dict[str, str]) -> str:
        """Return a per-host label for display in results.

        Args:
            host: Dict with 'name' and 'ip' keys.

        Returns:
            Human-readable string identifying this host's measurement.
        """
        return f"Total disk on {host['name']}"
