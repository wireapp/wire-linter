"""Checks the 1-minute load average on each VM host.

Connects to each discovered VM via SSH and reads /proc/loadavg to get
the 1-minute load average. Produces one data point per host with the
float load value.
"""

from __future__ import annotations

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


class VmLoadAverage(PerHostTarget):
    """Checks 1-minute load average on each VM discovers hosts via kubectl
    node labels, then SSHes in to read «/proc/loadavg» and extract the first field."""

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "1-minute load average"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Load above the CPU count means the VM is overloaded. Services become "
            "slow and may time out. Compare against the VM's core count."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because load average is dimensionless."""
        return ""

    def get_hosts(self) -> list[dict[str, str]]:
        """Returns the list of VM hosts to check (sourced from kubectl node labels)."""
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> float:
        """SSH in and parse the 1-minute load average from «/proc/loadavg».
        Returns a float (e.g. 0.42)."""
        self.terminal.step(f"Checking load average on {host['name']}...")

        result = self.run_ssh(host["ip"], "cat /proc/loadavg")
        fields = result.stdout.strip().split()

        if not fields:
            raise RuntimeError(f"Empty /proc/loadavg output on {host['name']}")

        try:
            return float(fields[0])
        except ValueError:
            raise RuntimeError(f"Unexpected /proc/loadavg format on {host['name']}: {result.stdout!r}")

    def description_for_host(self, host: dict[str, str]) -> str:
        """Returns a per-host label for display in results."""
        return f"1-minute load average on {host['name']}"
