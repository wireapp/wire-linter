"""Checks how many CPU cores the admin host has.

We run «nproc» to count the available cores and return that as an integer.
This helps verify the host isn't underpowered for running Wire.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class CpuCount(BaseTarget):
    """Counts CPU cores on the admin host.

    Since the runner IS the admin host, we execute «nproc» locally
    and return the integer count.
    """

    @property
    def description(self) -> str:
        return "Number of CPU cores on admin host"

    @property
    def explanation(self) -> str:
        return (
            "Admin host needs enough «CPU» cores or kubectl, helm, and Docker "
            "commands will crawl or timeout."
        )

    @property
    def unit(self) -> str:
        return "cores"

    def collect(self) -> int:
        """Fetch the CPU core count via «nproc»."""
        result = self.run_local(["nproc"])
        count: int = int(result.stdout.strip())

        # Summarize for the health report
        self._health_info = f"Admin host has {count} CPU core{'s' if count != 1 else ''}"

        return count
