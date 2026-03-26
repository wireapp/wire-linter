"""Counts PostgreSQL nodes (primary + standbys) from repmgr cluster show output.

We parse the pipe-separated table that repmgr spits out and just count up the
valid data rows each one is a PostgreSQL node in the replication cluster.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class PostgresqlNodeCount(BaseTarget):
    """Counts PostgreSQL nodes (primary + standbys).

    SSHs to the PostgreSQL host, runs repmgr cluster show, and counts the data
    rows in whatever pipe-separated table it returns.
    """

    # Uses SSH to reach PostgreSQL nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """How many PostgreSQL nodes are online."""
        return "Number of PostgreSQL nodes"

    @property
    def explanation(self) -> str:
        """Primary + standbys in repmgr. Fewer nodes = a standby died = failover capacity tanked."""
        return (
            "Counts primary + standby nodes registered in repmgr. Fewer nodes "
            "than expected means a standby is down and failover capacity is reduced."
        )

    @property
    def unit(self) -> str:
        """Measured in nodes."""
        return "nodes"

    def collect(self) -> int:
        """Count the number of PostgreSQL nodes registered in repmgr.

        Returns:
            Integer count of data rows in the repmgr cluster show table.

        Raises:
            RuntimeError: If the repmgr output contains no parseable data rows.
        """
        # Tell the operator what we're doing
        self.terminal.step("Counting PostgreSQL nodes...")

        # Run repmgr as postgres user (avoids permission headaches).
        # Config file location varies by version (/etc/repmgr/17-main/repmgr.conf, etc),
        # so we find it dynamically makes this work across PostgreSQL versions.
        result = self.run_db_command(
            self.config.databases.postgresql,
            "REPMGR_CONF=$(find /etc/repmgr -name repmgr.conf -type f 2>/dev/null | head -1);"
            " sudo -u postgres repmgr -f \"${REPMGR_CONF:-/etc/repmgr.conf}\" cluster show",
        )

        # Break output into lines so we can inspect each row
        lines: list[str] = result.stdout.strip().split("\n")

        # Count up valid node rows
        count: int = 0

        for line in lines:
            # Skip separator lines (---), headers (ID), and anything without pipes
            if "|" not in line or "---" in line or "ID" in line:
                continue

            # Split and check if it's got enough columns to be an actual node entry
            parts: list[str] = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                count += 1

        # No rows parsed = table was empty or format got messed up
        if count == 0:
            raise RuntimeError("Could not parse repmgr output")

        # Summarize what we found for the health report
        self._health_info = f"PostgreSQL cluster has {count} node{'s' if count != 1 else ''} (primary + standbys)"

        return count
