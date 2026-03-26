"""Checks root filesystem disk usage percentage on each VM host.

Connects to each discovered VM (kubenodes and datanodes) via SSH and runs
df to get the root filesystem usage as a percentage. Produces one data point
per host with the integer percentage value.
"""

from __future__ import annotations

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


class VmDiskUsage(PerHostTarget):
    """Checks disk usage on each VM discovers hosts via kubectl node labels,
    then SSHes in to read root partition usage from «df» output."""

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Disk usage"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "A full disk on any VM can crash its services. Above 90% is critical, "
            "above 75% is a warning. Checks the root partition on each VM."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the value."""
        return "%"

    def get_hosts(self) -> list[dict[str, str]]:
        """Returns the list of VM hosts to check (sourced from kubectl node labels)."""
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> int:
        """SSH in and parse root filesystem usage from «df» output.
        Returns the percentage as an integer (e.g. 42 for 42%)."""
        self.terminal.step(f"Checking disk usage on {host['name']}...")

        # Get df output for root mount, skip the header line
        result = self.run_ssh(host["ip"], "df -h / | tail -1")

        fields: list[str] = result.stdout.strip().split()

        if len(fields) < 5:
            raise RuntimeError(f"Unexpected df output on {host['name']}: expected >= 5 fields, got {len(fields)}")

        # Field 4 is the Use% column strip the % sign before parsing
        usage_str: str = fields[4].rstrip("%")

        return int(usage_str)

    def description_for_host(self, host: dict[str, str]) -> str:
        """Returns a per-host label for display in results."""
        return f"Disk usage on {host['name']} ({host['ip']})"
