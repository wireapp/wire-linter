"""Checks 1-minute load average on the admin host.

Pulls the 1-minute load average from «/proc/loadavg». The first field is what
we care about here. If this number climbs above your CPU count, you've got
trouble: processes are piling up waiting for CPU time.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class LoadAverage(BaseTarget):
    """Checks 1-minute load average on the admin host.

    Reads «/proc/loadavg» directly and grabs the first field. Since we're
    running on the admin host, we can read this directly from the kernel.
    """

    @property
    def description(self) -> str:
        return "1-minute load average on admin host"

    @property
    def explanation(self) -> str:
        """Why this check matters."""
        return (
            "If «load average» goes above your CPU count, processes are backing up "
            "waiting for CPU time. Check this against your actual core count."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement. Load average has no unit."""
        return ""

    def collect(self) -> float:
        """Read the 1-minute load average.

        Returns:
            The 1-minute load average as a float.

        Raises:
            RuntimeError: If we can't read or parse «/proc/loadavg».
        """
        # Get the raw kernel data
        result = self.run_local(["cat", "/proc/loadavg"])

        # Split the output: first field is 1-min, then 5-min, then 15-min
        fields: list[str] = result.stdout.strip().split()

        if not fields:
            raise RuntimeError("Empty /proc/loadavg output")

        try:
            load: float = float(fields[0])
        except ValueError:
            raise RuntimeError(f"Unexpected /proc/loadavg format: {result.stdout!r}")

        # Summarize for the health report
        self._health_info = f"Admin host 1-minute load average is {load}"

        return load
