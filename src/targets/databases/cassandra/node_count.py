"""Counts the number of Cassandra nodes visible in nodetool status output.

Parses nodetool status output to count lines with valid 2-character status
codes (first char U/D, second char N/L/J/M), representing cluster nodes
regardless of their state.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class CassandraNodeCount(BaseTarget):
    """Counts Cassandra nodes in the cluster.

    Connects to the Cassandra host via SSH, runs nodetool status,
    and counts lines that match the node status pattern.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Number of Cassandra nodes in the cluster"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Tracks how many Cassandra nodes are in the ring. A drop in count "
            "means a node left or isn't reachable, risking data availability."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement for the returned value."""
        return "nodes"

    def collect(self) -> int:
        """Count the number of Cassandra nodes in the cluster.

        Returns:
            Integer count of nodes visible in nodetool status.

        Raises:
            RuntimeError: If nodetool output cannot be parsed.
        """
        # Inform the operator which host and command will be executed
        self.terminal.step("Counting Cassandra nodes...")

        # Run nodetool status on the configured Cassandra host
        result = self.run_db_command(
            self.config.databases.cassandra,
            "nodetool status",
        )

        # Split output into lines for line-by-line parsing
        lines: list[str] = result.stdout.strip().split("\n")

        # Accumulator for valid node status lines
        count: int = 0

        for line in lines:
            # Normalize indented lines by stripping whitespace
            stripped: str = line.strip()

            # Node status lines start with a 2-char code: first char U/D (up/down),
            # second char N/L/J/M (normal/leaving/joining/moving)
            if len(stripped) >= 2 and stripped[0] in "UD" and stripped[1] in "NLJM":
                count += 1

        # No nodes found means the output format wasn't recognized
        if count == 0:
            raise RuntimeError("Couldn't parse nodetool status output - no nodes found")

        # Summarize what we found for the health report
        self._health_info = f"Cassandra cluster has {count} node{'s' if count != 1 else ''}"

        return count
