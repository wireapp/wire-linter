"""Checks if the system clock is actually synced via NTP.

Tries `timedatectl show` first since it's machine-readable and more reliable
on newer systemd. Falls back to `timedatectl status` if that doesn't have
what we need older systems just don't support the show format. If your
clock isn't synced, TLS certs will fail to validate and logs won't line up.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class NtpSynchronized(BaseTarget):
    """Checks if the system clock is synchronized via NTP.

    Starts with timedatectl show since it's clean key=value format, easier to parse.
    If that doesn't have the NTPSynchronized key (older systemd), falls back to
    timedatectl status which is messier but gets the job done.
    """

    @property
    def description(self) -> str:
        """What we're actually checking."""
        return "System clock is synchronized via NTP"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "If your clock is out of sync, TLS certs won't validate and your logs "
            "won't line up with anything else. NTP synced means you're healthy."
        )

    @property
    def unit(self) -> str:
        """Nothing to measure here, just yes or no."""
        return ""

    def collect(self) -> bool:
        """Check if the clock is synced.

        Returns True if synced, False otherwise.
        """
        # timedatectl show gives us clean key=value output, easy to parse
        result = self.run_local(["timedatectl", "show"])

        # Look for NTPSynchronized key, check each line individually
        for line in result.stdout.strip().split("\n"):
            if line.startswith("NTPSynchronized="):
                # Pull out the value, case doesn't matter but normalize it
                value: str = line.split("=", 1)[1].strip()
                synced: bool = value.lower() == "yes"
                self._health_info = "Clock synchronized" if synced else "Clock NOT synchronized"
                return synced

        # Older systemd doesn't put NTPSynchronized in show output, so try status instead
        result2 = self.run_local(["timedatectl", "status"])

        # status output has something like "System clock synchronized: yes"
        for line in result2.stdout.strip().split("\n"):
            if "synchronized" in line.lower():
                synced = "yes" in line.lower()
                self._health_info = "Clock synchronized" if synced else "Clock NOT synchronized"
                return synced

        # Couldn't find what we needed from either command, assume unsynced
        self._health_info = "Could not determine NTP sync status"
        return False
