"""Checks that required Cassandra keyspaces exist.

Missing keyspaces after migration or fresh install means the
corresponding Wire service won't work at all. Required keyspaces:
brig, galley, spar, gundeck.

Primary method: SSH tunnel + native CQL protocol (no remote dependencies).
Fallback: cqlsh on the Cassandra node, then on the admin host.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.cql_types import CqlResult


# Wire services that must have their own Cassandra keyspace
_REQUIRED_KEYSPACES: list[str] = ["brig", "galley", "spar", "gundeck"]


class CassandraKeyspaces(BaseTarget):
    """Checks that required Cassandra keyspaces exist.

    Queries system_schema.keyspaces via native CQL protocol through
    an SSH tunnel. Falls back to cqlsh if the tunnel fails.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Required Cassandra keyspaces present"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Missing keyspaces mean the Wire service can't function. "
            "Healthy when brig, galley, spar, and gundeck all exist."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check that all required keyspaces exist in Cassandra.

        Returns:
            True if all required keyspaces are present, False otherwise.

        Raises:
            RuntimeError: If no method can retrieve keyspace data.
        """
        self.terminal.step("Checking Cassandra keyspaces...")

        existing_keyspaces: set[str] | None = self._keyspaces_via_cql()

        if existing_keyspaces is None:
            # Native CQL failed, fall back to cqlsh
            existing_keyspaces = self._keyspaces_via_cqlsh()

        if existing_keyspaces is None:
            raise RuntimeError(
                "Couldn't retrieve keyspace list - native CQL tunnel "
                "and cqlsh both failed"
            )

        missing: list[str] = [
            ks for ks in _REQUIRED_KEYSPACES
            if ks not in existing_keyspaces and f"{ks}_test" not in existing_keyspaces
        ]

        all_present: bool = len(missing) == 0

        if all_present:
            self._health_info = f"All {len(_REQUIRED_KEYSPACES)} required keyspaces present"
        else:
            self._health_info = f"Missing keyspaces: {', '.join(missing)}"

        return all_present

    def _keyspaces_via_cql(self) -> set[str] | None:
        """Try to get keyspace names via native CQL protocol.

        Returns:
            Set of keyspace names, or None if the connection failed.
        """
        try:
            result: CqlResult = self.run_cql_query(
                "SELECT keyspace_name FROM system_schema.keyspaces"
            )
            return {
                str(row[0]) for row in result.rows
                if row[0] is not None
            }
        except Exception as exc:
            self.terminal.step(
                f"Native CQL failed ({exc}), falling back to cqlsh..."
            )
            return None

    def _keyspaces_via_cqlsh(self) -> set[str] | None:
        """Get keyspace names via cqlsh as fallback.

        Returns:
            Set of keyspace names, or None if cqlsh failed.
        """
        result = self.run_cqlsh("DESCRIBE KEYSPACES")
        output: str = result.stdout.strip()
        if not output:
            return None
        # DESCRIBE KEYSPACES returns whitespace-separated keyspace names
        return set(output.split())
