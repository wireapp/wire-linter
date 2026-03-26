"""Checks memory usage in GiB on each VM host.

Connects to each discovered VM via SSH and runs free -m to get the used
memory in megabytes, then converts to GiB. Produces one data point per
host with the float GiB value rounded to one decimal place.
"""

from __future__ import annotations

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


class VmMemoryUsed(PerHostTarget):
    """Checks memory used on each VM discovers hosts via kubectl node labels,
    then SSHes in to parse «free -m» output and convert MiB to GiB."""

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Memory used"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "High memory usage leads to OOM kills. Combined with memory total, "
            "lets you compute utilization percentage per VM."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the value."""
        return "Gi"

    def get_hosts(self) -> list[dict[str, str]]:
        """Returns the list of VM hosts to check (sourced from kubectl node labels)."""
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> float:
        """SSH in and parse used memory from «free -m» output.
        Returns GiB of used memory, rounded to one decimal place."""
        self.terminal.step(f"Checking memory on {host['name']}...")

        result = self.run_ssh(host["ip"], "free -m")
        lines: list[str] = result.stdout.strip().split("\n")

        mem_line: str = ""
        for line in lines:
            if line.startswith("Mem:"):
                mem_line = line
                break

        if not mem_line:
            raise RuntimeError(f"Could not find 'Mem:' line in free output on {host['name']}")

        fields: list[str] = mem_line.split()

        if len(fields) < 3:
            raise RuntimeError(f"Unexpected free output on {host['name']}: expected >= 3 fields, got {len(fields)}")

        # Field 2 is the used column in MiB
        used_mb: int = int(fields[2])

        # Convert MiB to GiB (1024 MiB = 1 GiB)
        used_gi: float = round(used_mb / 1024, 1)

        return used_gi

    def description_for_host(self, host: dict[str, str]) -> str:
        """Returns a per-host label for display in results."""
        return f"Memory used on {host['name']}"
