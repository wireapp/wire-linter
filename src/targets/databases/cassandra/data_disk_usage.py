"""Checks Cassandra data directory disk usage on datanodes.

Cassandra data often lives on a separate mount (/mnt/cassandra/data/) and
can fill up even when the root filesystem looks fine. Falls back to
/var/lib/cassandra if the dedicated mount doesn't exist.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class CassandraDataDiskUsage(BaseTarget):
    """Checks disk usage of the Cassandra data directory.

    SSHes to the Cassandra datanode and runs df on the data directory,
    reporting the usage percentage of the partition holding data.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Cassandra data directory disk usage"

    @property
    def explanation(self) -> str:
        """Why we're checking and what's healthy vs unhealthy."""
        return (
            "Cassandra data often lives on a separate mount that can fill up even when "
            "root looks fine. Above 90% is critical, above 75% is a warning."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the value."""
        return "%"

    def collect(self) -> int:
        """Check disk usage on the Cassandra data partition.

        Returns:
            Integer percentage of disk used on the Cassandra data partition.

        Raises:
            RuntimeError: If df output cannot be parsed.
        """
        self.terminal.step("Checking Cassandra data disk usage...")

        # Try common Cassandra data paths, mount point varies by installation
        result = self.run_db_command(
            self.config.databases.cassandra,
            "df -h /mnt/cassandra/data 2>/dev/null"
            " || df -h /var/lib/cassandra 2>/dev/null"
            " || df -h /",
        )

        # Parse df output, take the last line which has the actual data
        lines: list[str] = [line for line in result.stdout.strip().split("\n") if line.strip()]

        if len(lines) < 2:
            raise RuntimeError("Unexpected df output on Cassandra datanode")

        # Last non-empty line is the data we want
        data_line: str = lines[-1]
        fields: list[str] = data_line.split()

        if len(fields) < 5:
            raise RuntimeError(f"Couldn't parse df output: {data_line}")

        # Field 4 is the « Use% » column
        usage_str: str = fields[4].rstrip("%")
        try:
            usage: int = int(usage_str)
        except ValueError:
            raise RuntimeError(f"Could not parse disk usage from df output: {data_line}")

        # Last field is the mount point
        mount_point: str = fields[-1] if len(fields) >= 6 else "?"

        if usage >= 90:
            self._health_info = f"CRITICAL: {usage}% used on {mount_point}"
        elif usage >= 75:
            self._health_info = f"WARNING: {usage}% used on {mount_point}"
        else:
            self._health_info = f"{usage}% used on {mount_point}"

        return usage
