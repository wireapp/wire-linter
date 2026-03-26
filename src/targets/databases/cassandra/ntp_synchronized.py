"""Checks NTP synchronization on Cassandra datanodes.

Time drift breaks Cassandra quorum. This target SSHes to the
Cassandra host and checks timedatectl for NTP sync status.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class CassandraNtpSynchronized(BaseTarget):
    """Checks NTP synchronization on the Cassandra datanode.

    Connects to the configured Cassandra host via SSH and runs
    timedatectl to verify NTP synchronization is active.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "NTP synchronized on Cassandra datanode"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Clock drift between nodes breaks quorum consistency and causes "
            "data corruption. Healthy when timedatectl reports NTP is synchronized."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check NTP sync status on the Cassandra datanode via timedatectl.

        Returns:
            True if NTP is synchronized, False otherwise.
        """
        self.terminal.step("Checking NTP sync on Cassandra datanode...")

        result = self.run_db_command(
            self.config.databases.cassandra,
            "timedatectl show 2>/dev/null || timedatectl status",
        )

        output: str = result.stdout.strip()

        # Try machine-readable format first (NTPSynchronized=yes)
        for line in output.split("\n"):
            if line.startswith("NTPSynchronized="):
                value: str = line.split("=", 1)[1].strip()
                synced: bool = value.lower() == "yes"
                self._health_info = "Clock synchronized" if synced else "Clock not synchronized"
                return synced

        # Fall back to human-readable format
        for line in output.split("\n"):
            if "synchronized" in line.lower():
                synced = "yes" in line.lower()
                self._health_info = "Clock synchronized" if synced else "Clock not synchronized"
                return synced

        self._health_info = "Could not determine NTP sync status"
        return False
