"""Checks PostgreSQL replication health via repmgr cluster show.

Parses repmgr's table output to see if all nodes are up, counts primaries
and standbys, and tells you if things look healthy or degraded.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class PostgresqlReplicationStatus(BaseTarget):
    """Checks PostgreSQL replication status via repmgr.

    Connects to the PostgreSQL host via SSH, runs repmgr cluster show,
    and inspects each node's role and status to assess overall replication health.
    """

    # Uses SSH to reach PostgreSQL nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "PostgreSQL repmgr cluster status"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "We need all repmgr nodes running and at least one primary. "
            "If any node's down or there's no primary, we're degraded."
        )

    def collect(self) -> str:
        """Assess PostgreSQL replication health from repmgr cluster show output.

        Returns:
            "healthy" if all nodes are running and at least one primary exists,
            "degraded" if any node is not running or no primary is found.

        Raises:
            RuntimeError: If the repmgr output contains no parseable data rows.
        """
        # Tell the operator what we're doing
        self.terminal.step("Checking PostgreSQL replication status...")

        # Run repmgr as postgres user so we don't hit permission errors.
        # Auto-detect the config file path since it moves around depending on the version.
        result = self.run_db_command(
            self.config.databases.postgresql,
            "REPMGR_CONF=$(find /etc/repmgr -name repmgr.conf -type f 2>/dev/null | head -1);"
            " sudo -u postgres repmgr -f \"${REPMGR_CONF:-/etc/repmgr.conf}\" cluster show",
        )

        output: str = result.stdout.strip()

        # Split into lines for row-by-row inspection of the table
        lines: list[str] = output.split("\n")

        # Track aggregate state across all node rows
        all_running: bool = True
        node_count: int = 0
        primary_count: int = 0
        standby_count: int = 0

        for line in lines:
            # Skip separator lines (---), header row (contains "Node ID"), and anything without a pipe
            if "|" not in line or "---" in line or "Node ID" in line:
                continue

            # Split the row into columns; repmgr table has at minimum 4 fields
            parts: list[str] = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                node_count += 1

                # Role's at index 2, lowercase it for safe comparison
                role: str = parts[2].strip().lower()

                # Status's at index 3, lowercase for safe comparison
                status: str = parts[3].strip().lower()

                # Track role distribution so our description's useful
                if "primary" in role:
                    primary_count += 1
                elif "standby" in role:
                    standby_count += 1

                # Any node down = cluster's degraded, no matter what role it had.
                # Use exact match because 'running' is a substring of 'not running',
                # so a substring check would incorrectly pass 'not running' as healthy.
                if status.strip() != "running":
                    all_running = False

        # Zero rows = table was empty or the format changed
        if node_count == 0:
            raise RuntimeError("Could not parse repmgr cluster show output")

        # Build a nice description with the node counts
        if all_running and primary_count >= 1:
            self._dynamic_description = (
                f"PostgreSQL {node_count}-node repmgr cluster, "
                f"primary + {standby_count} standbys all running"
            )
            self._health_info = f"Primary + {standby_count} standbys all running"
            return "healthy"

        self._health_info = f"{node_count} nodes, {primary_count} primary, not all running"
        return "degraded"
