"""Checks whether all Cassandra nodes report Up/Normal status via nodetool status.

Parses nodetool status output to extract 2-character status codes (UN, DN,
UL, etc.) for each node. Returns "UN" if all nodes are Up/Normal, otherwise
returns the first non-UN status code found.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class CassandraClusterStatus(BaseTarget):
    """Checks Cassandra cluster status via nodetool.

    Connects to the Cassandra host via SSH, runs nodetool status, and
    looks at status codes for every node in the ring.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "All Cassandra nodes are Up/Normal"

    @property
    def explanation(self) -> str:
        """Why we're checking and what's healthy vs unhealthy."""
        return (
            "Nodes that are Down or Leaving/Joining/Moving can't serve reads or writes "
            "reliably. It's healthy when every node reports UN (Up/Normal) in nodetool status."
        )

    def collect(self) -> str:
        """Check whether all Cassandra nodes are in Up/Normal (UN) state.

        Returns:
            "UN" if all nodes are Up/Normal, otherwise the first non-UN
            status code found (e.g. "DN", "UL", "UJ").

        Raises:
            RuntimeError: If nodetool output contains no recognisable node lines.
        """
        # Tell the operator what's about to run
        self.terminal.step("Running nodetool status on Cassandra host...")

        # Run nodetool status on the Cassandra host via SSH
        result = self.run_db_command(
            self.config.databases.cassandra,
            "nodetool status",
        )

        # Split output into lines, so we can look at each node entry
        lines: list[str] = result.stdout.strip().split("\n")

        # Collect per-node status codes for evaluation
        statuses: list[str] = []

        for line in lines:
            # Strip indentation so the status code starts at position 0
            stripped: str = line.strip()

            # Node status lines start with a 2-char code. First char is U/D (up/down),
            # second is N/L/J/M (normal/leaving/joining/moving)
            if len(stripped) >= 2 and stripped[0] in "UD" and stripped[1] in "NLJM":
                statuses.append(stripped[:2])

        # No matched lines means the output format didn't match or the tool failed
        if not statuses:
            raise RuntimeError("Couldn't parse nodetool status output, no node status lines found")

        # All nodes healthy, so we're done
        if all(s == "UN" for s in statuses):
            # Secondary health info (just for display)
            self._health_info = f"All {len(statuses)} nodes Up/Normal"
            return "UN"

        # Return the first degraded status so callers know what's happening
        for s in statuses:
            if s != "UN":
                # Secondary health info (just for display)
                non_un: int = sum(1 for x in statuses if x != "UN")
                self._health_info = f"{non_un}/{len(statuses)} nodes not Up/Normal"
                return s

        return "UN"
