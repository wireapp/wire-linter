"""Checks that the Cassandra spar keyspace has the expected schema tables.

An incomplete spar schema (missing idp or issuer_idp tables) means SAML
SSO configuration is not persisted and wire-server cannot perform SSO
logins. See JCT-164.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.cql_types import CqlResult


# Tables that the spar service requires for SAML IdP storage
_REQUIRED_SPAR_TABLES: list[str] = [
    "idp",
    "issuer_idp",
    "user",
    "bind",
]


class CassandraSparTables(BaseTarget):
    """Checks that the Cassandra spar keyspace has the required tables.

    Queries system_schema.tables filtered by keyspace_name='spar' to
    verify the SAML identity-provider storage schema is there.
    Healthy when all required tables exist.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Cassandra spar keyspace tables"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Missing spar schema tables mean SAML SSO config can't be saved. "
            "wire-server needs idp, issuer_idp, user, and bind tables in spar "
            "keyspace for SSO logins to work (JCT-164)."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check that all required spar keyspace tables exist.

        Returns:
            True if all required tables are present, False otherwise.

        Raises:
            RuntimeError: If the Cassandra query cannot be executed.
        """
        self.terminal.step("Checking Cassandra spar schema tables...")

        existing_tables: set[str] | None = self._tables_via_cql()

        if existing_tables is None:
            # Fall back to cqlsh if the native CQL tunnel failed
            existing_tables = self._tables_via_cqlsh()

        if existing_tables is None:
            raise RuntimeError(
                "Couldn't retrieve spar table list - "
                "native CQL and cqlsh both failed"
            )

        missing: list[str] = [
            t for t in _REQUIRED_SPAR_TABLES if t not in existing_tables
        ]

        all_present: bool = len(missing) == 0

        if all_present:
            self._health_info = (
                f"All {len(_REQUIRED_SPAR_TABLES)} required spar tables present "
                f"({len(existing_tables)} total in spar keyspace)"
            )
        else:
            self._health_info = f"Missing spar tables: {', '.join(missing)}"

        return all_present

    def _tables_via_cql(self) -> set[str] | None:
        """Query spar table names via native CQL protocol.

        Returns:
            Set of table names in the spar keyspace, or None on failure.
        """
        try:
            result: CqlResult = self.run_cql_query(
                "SELECT table_name FROM system_schema.tables "
                "WHERE keyspace_name='spar'"
            )
            return {str(row[0]) for row in result.rows if row[0] is not None}
        except Exception as exc:
            self.terminal.step(f"Native CQL failed ({exc}), falling back to cqlsh...")
            return None

    def _tables_via_cqlsh(self) -> set[str] | None:
        """Query spar table names via cqlsh as fallback.

        Returns:
            Set of table names, or None if cqlsh also failed.
        """
        result = self.run_cqlsh(
            "SELECT table_name FROM system_schema.tables WHERE keyspace_name='spar'"
        )
        output: str = result.stdout.strip()

        if not output:
            return None

        tables: set[str] = set()

        for line in output.split("\n"):
            stripped: str = line.strip()
            # Skip header row, separator lines, and the cqlsh result footer like "(4 rows)" or "(1 row)"
            if not stripped or "table_name" in stripped or stripped.startswith("-"):
                continue
            if re.match(r'^\(\d+ rows?\)$', stripped):
                continue
            # Each data line is a single table name
            tables.add(stripped)

        return tables if tables else None
