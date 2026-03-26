"""Checks total physical memory in GiB on each VM host.

Connects to each discovered VM via SSH and runs free -m to get the
total memory in megabytes, then converts to GiB. Together with
memory_used, allows the UI to compute utilization percentage.
"""

from __future__ import annotations

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


class VmMemoryTotal(PerHostTarget):
    """Checks total physical memory on each VM discovers hosts via kubectl
    node labels, then SSHes in to parse «free -m» output and convert MiB to GiB."""

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Memory total"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Records total physical memory per VM. Combined with memory used, "
            "lets you assess memory pressure and plan capacity."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the value."""
        return "Gi"

    def get_hosts(self) -> list[dict[str, str]]:
        """Returns the list of VM hosts to check."""
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> float:
        """SSH in and parse total memory from «free -m» output.
        Returns GiB of total physical memory, rounded to one decimal place."""
        self.terminal.step(f"Checking total memory on {host['name']}...")

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

        if len(fields) < 2:
            raise RuntimeError(f"Unexpected free output on {host['name']}: expected >= 2 fields, got {len(fields)}")

        # Field 1 is the total column in MiB; guard against non-numeric output
        try:
            total_mb: int = int(fields[1])
        except (ValueError, TypeError):
            raise RuntimeError(
                f"Could not parse memory total on {host['name']}: expected integer, got {fields[1]!r}"
            )

        # Convert MiB to GiB
        total_gi: float = round(total_mb / 1024, 1)

        return total_gi

    def description_for_host(self, host: dict[str, str]) -> str:
        """Returns a per-host label for display in results."""
        return f"Total memory on {host['name']}"
