"""Counts SAML identity providers configured in the Cassandra spar keyspace.

A zero count means SAML SSO is not configured or all IdPs have been
deleted. This is significant when brig's optSettings.setSSOEnabled=true
because users will not be able to log in via SSO. See JCT-164.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.cql_types import CqlResult


class CassandraSparIdpCount(BaseTarget):
    """Counts configured SAML identity providers in the spar Cassandra keyspace.

    Queries spar.idp table (or spar.user for older schemas) and
    returns how many identity providers are configured. Zero means
    SAML SSO isn't set up, even if brig's SSO flag is enabled.
    """

    # Uses SSH to reach Cassandra nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Cassandra spar SAML identity provider count"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "If brig's setSSOEnabled is true but no IdPs are registered in "
            "spar.idp, users can't log in via SSO. "
            "A missing spar.issuer_idp row is the usual cause (JCT-164)."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the collected value."""
        return "IdPs"

    def collect(self) -> int:
        """Count SAML identity providers in the spar Cassandra keyspace.

        Returns:
            Number of rows in the spar.idp table (count of configured IdPs).

        Raises:
            RuntimeError: If the Cassandra query cannot be executed.
        """
        self.terminal.step("Counting SAML IdPs in Cassandra spar keyspace...")

        idp_count: int | None = self._count_via_cql()

        if idp_count is None:
            idp_count = self._count_via_cqlsh()

        if idp_count is None:
            raise RuntimeError(
                "Couldn't count spar.idp rows - native CQL and cqlsh both failed"
            )

        if idp_count == 0:
            self._health_info = (
                "No SAML IdPs registered in spar.idp. "
                "Severity depends on brig optSettings.setSSOEnabled - "
                "checked by the UI layer against kubernetes/configmaps/brig."
            )
        else:
            self._health_info = f"{idp_count} SAML IdP(s) configured in spar keyspace"

        return idp_count

    def _count_via_cql(self) -> int | None:
        """Count spar.idp rows via native CQL protocol.

        Returns:
            Row count, or None if the query failed.
        """
        try:
            result: CqlResult = self.run_cql_query("SELECT COUNT(*) FROM spar.idp")

            if result.rows:
                count_val: object = result.rows[0][0]
                return int(count_val) if count_val is not None else 0

            return 0
        except Exception as exc:
            self.terminal.step(f"Native CQL failed ({exc}), falling back to cqlsh...")
            return None

    def _count_via_cqlsh(self) -> int | None:
        """Count spar.idp rows via cqlsh as fallback.

        Returns:
            Row count, or None if cqlsh also failed.
        """
        result = self.run_cqlsh("SELECT COUNT(*) FROM spar.idp")
        output: str = result.stdout.strip()

        if not output:
            return None

        # cqlsh tabular output has separator lines like "------"
        # The data rows sit between the first and second separators.
        # Only parse integers from that region to avoid picking up
        # stray numbers from headers, footers, or timing lines.
        lines: list[str] = output.split("\n")
        in_data_region: bool = False

        for line in lines:
            stripped: str = line.strip()

            # Detect separator lines (e.g. "------" or "---+---")
            if stripped and all(ch in "-+" for ch in stripped):
                if in_data_region:
                    # Second separator ends the data region
                    break
                in_data_region = True
                continue

            if in_data_region:
                try:
                    value: int = int(stripped)
                    return value
                except ValueError:
                    continue

        return None
