"""Grabs how long the admin host has been running.

Runs « uptime -p » which spits out something like « up 3 days, 4 hours, 12 minutes ».
We strip the « up » part and give you just the duration. Low uptime is a red flag -
means something probably rebooted unexpectedly.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class Uptime(BaseTarget):
    """Checks how long the admin host's been up.

    We run « uptime -p » locally (since we're on the admin host) and pull
    out just the duration part, dropping the « up » prefix.
    """

    @property
    def description(self) -> str:
        """What we're checking just system uptime."""
        return "System uptime"

    @property
    def explanation(self) -> str:
        """Why we care about uptime and what it tells us."""
        return (
            "Low uptime means something crashed or rebooted - that's worth looking into. "
            "Basically we just track this so you know what's happening."
        )

    @property
    def unit(self) -> str:
        """No unit here we're returning text, not numbers."""
        return ""

    def collect(self) -> str:
        """Grab the current uptime and return it as a string.

        Returns:
            Something like « 3 days, 4 hours, 12 minutes ».
        """
        # uptime -p gives us a readable format on any system
        result = self.run_local(["uptime", "-p"])

        # Clean up whitespace first
        uptime_str: str = result.stdout.strip()

        # Drop the « up » prefix we just want the duration part
        if uptime_str.startswith("up "):
            uptime_str = uptime_str[3:]

        # Summarize for the health report
        self._health_info = f"Admin host up for {uptime_str}"

        return uptime_str
