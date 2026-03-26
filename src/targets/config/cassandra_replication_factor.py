"""Checks Cassandra replication factor vs node count.

Replication factor > nodes = schema migrations crash. Compares configured
factor against live node count from nodetool.

Tries (first success wins):
1. Native CQL via tunnel (no Python/cqlsh needed)
2. cassandra-migrations ConfigMap
3. cqlsh DESCRIBE KEYSPACE brig
4. nodetool describering (always available)
"""

from __future__ import annotations

# External
import ast
import re
from typing import Any, Callable

# Ours
from src.lib.base_target import BaseTarget
from src.lib.cql_types import CqlResult
from src.lib.yaml_parser import parse_yaml, get_nested


class CassandraReplicationFactor(BaseTarget):
    """Checks Cassandra replication factor vs node count.

    Tries multiple extraction methods, then compares against live node count.
    """

    # Uses SSH to reach Cassandra nodes for nodetool and CQL
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Cassandra replication factor vs node count"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Replication factor > live nodes = schema migrations crash. "
            "Healthy when RF <= node count."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool | str:
        """Compare replication factor against live node count.

        Tries each extraction method in order, reports which ones failed
        so you can diagnose the issue.

        Returns:
            True if RF <= node count, False if RF > node count,
            or the string "inconclusive" if the RF could not be determined
            by any of the four probe methods.

        Raises:
            RuntimeError: If node count can't be determined.
        """
        self.terminal.step("Checking Cassandra replication factor...")

        result = self.run_db_command(
            self.config.databases.cassandra,
            "nodetool status",
        )

        # Count only Up/Normal nodes (DN, UL, UJ, UM can't serve replicas)
        node_count: int = 0
        for line in result.stdout.strip().split("\n"):
            stripped: str = line.strip()
            if len(stripped) >= 2 and stripped[:2] == "UN":
                node_count += 1

        if node_count == 0:
            raise RuntimeError("Can't determine node count from nodetool status")

        # Try methods in order, first success wins
        methods: list[tuple[str, Callable[[], tuple[int | None, str]]]] = [
            ("native CQL query", self._rf_from_cql),
            ("ConfigMap cassandra-migrations", self._rf_from_configmap),
            ("cqlsh DESCRIBE KEYSPACE brig", self._rf_from_cqlsh),
            ("nodetool describering brig", self._rf_from_describering),
        ]

        replication_factor: int | None = None
        failure_reasons: list[str] = []

        for method_name, method_fn in methods:
            rf, reason = method_fn()
            if rf is not None:
                replication_factor = rf
                break
            failure_reasons.append(f"{method_name}: {reason}")

        if replication_factor is None:
            reasons_str: str = ". ".join(failure_reasons)
            self._health_info = (
                f"Can't determine RF ({node_count} nodes). "
                f"Tried: {reasons_str}"
            )
            # Return a sentinel string instead of True so the UI can render
            # this as a warning rather than a healthy pass. Returning True here
            # would make a fully-unreachable or misconfigured Cassandra cluster
            # appear green, which masks real problems.
            return "inconclusive"

        valid: bool = replication_factor <= node_count

        if valid:
            self._health_info = f"RF={replication_factor}, nodes={node_count} OK"
        else:
            self._health_info = (
                f"CRITICAL: RF={replication_factor} > nodes={node_count}, "
                f"migrations will fail"
            )

        return valid

    def _rf_from_cql(self) -> tuple[int | None, str]:
        """Extract RF via native CQL protocol.

        Queries system_schema.keyspaces directly, no cqlsh/Python needed.

        Returns:
            Tuple of (replication_factor, failure_reason).
        """
        try:
            result: CqlResult = self.run_cql_query(
                "SELECT replication FROM system_schema.keyspaces "
                "WHERE keyspace_name = 'brig'"
            )
        except Exception as exc:
            return (None, f"tunnel/connection failed: {exc}")

        if not result.rows:
            return (None, "brig keyspace not found in system_schema")

        # Replication is a map like:
        # {'class': 'SimpleStrategy', 'replication_factor': '3'}
        replication_map: dict[str, str] = result.rows[0][0] or {}

        # SimpleStrategy case
        if 'replication_factor' in replication_map:
            try:
                rf_val: int = int(replication_map['replication_factor'])
                if rf_val > 0:
                    return (rf_val, "")
                return (None, "replication_factor is 0 (invalid)")
            except (ValueError, TypeError):
                return (None, "replication_factor isn't an int")

        # NetworkTopologyStrategy case
        rf_values: list[int] = []
        for key, val in replication_map.items():
            if key == 'class':
                continue
            try:
                rf_values.append(int(val))
            except (ValueError, TypeError):
                continue

        if rf_values:
            max_rf: int = max(rf_values)
            if max_rf > 0:
                return (max_rf, "")
            return (None, "all RF values in replication map are 0 (invalid)")

        return (None, "replication map present but no RF values")

    def _rf_from_configmap(self) -> tuple[int | None, str]:
        """Extract RF from cassandra-migrations ConfigMap.

        Returns:
            Tuple of (replication_factor, failure_reason).
        """
        _result_cm, cm_data = self.run_kubectl("configmap/cassandra-migrations")

        if not isinstance(cm_data, dict):
            return (None, "ConfigMap not found or not parseable")

        cm_data_section: dict[str, str] = cm_data.get("data", {})

        if not cm_data_section:
            return (None, "ConfigMap has no data section")

        # Look through all data keys for a replication factor setting
        for _key, value in cm_data_section.items():
            if "replicationFactor" not in value and "replication_factor" not in value:
                continue

            try:
                parsed: dict[str, Any] = parse_yaml(value)
                rf: Any = (
                    get_nested(parsed, "cassandra.replicationFactor")
                    or get_nested(parsed, "replicationFactor")
                )
                if rf is not None:
                    rf_int: int = int(rf)
                    if rf_int > 0:
                        return (rf_int, "")
            except (ValueError, TypeError):
                pass

        return (None, "no replicationFactor field found in ConfigMap data keys")

    def _rf_from_cqlsh(self) -> tuple[int | None, str]:
        """Extract RF from cqlsh DESCRIBE KEYSPACE.

        Handles SimpleStrategy and NetworkTopologyStrategy. Tries
        Cassandra node first, falls back to admin host.

        Returns:
            Tuple of (replication_factor, failure_reason).
        """
        rf_result = self.run_cqlsh("DESCRIBE KEYSPACE brig")

        output: str = rf_result.stdout.strip()
        if not output:
            return (None, "cqlsh unavailable")

        # SimpleStrategy case
        simple_match: re.Match[str] | None = re.search(
            r"['\"]replication_factor['\"]\s*:\s*['\"]?(\d+)", output,
        )
        if simple_match:
            rf_simple: int = int(simple_match.group(1))
            if rf_simple > 0:
                return (rf_simple, "")
            return (None, "replication_factor matched but is 0 (invalid)")

        # NetworkTopologyStrategy case - extract the replication map dict,
        # parse it structurally, then discard non-DC keys ('class' and any
        # future string-keyed non-integer entries) rather than relying on a
        # regex negative-lookahead that only excludes 'class'.
        map_match: re.Match[str] | None = re.search(r"\{[^}]+\}", output)
        if map_match:
            # Cassandra DESCRIBE output uses single-quoted strings; ast.literal_eval
            # requires valid Python literals, which single-quoted strings already are.
            try:
                replication_map: dict[str, str] = ast.literal_eval(map_match.group(0))
            except (ValueError, SyntaxError):
                replication_map = {}

            # Remove the strategy class entry - all remaining keys are DC names.
            replication_map.pop("class", None)

            # Keep only entries whose values are pure digit strings (RF values).
            rf_values: list[int] = [
                int(val)
                for val in replication_map.values()
                if isinstance(val, str) and val.isdigit()
            ]
            if rf_values:
                max_rf_nts: int = max(rf_values)
                if max_rf_nts > 0:
                    return (max_rf_nts, "")
                return (None, "all NTS RF values are 0 (invalid)")

        return (None, "DESCRIBE output present but replication dict not matched")

    def _rf_from_describering(self) -> tuple[int | None, str]:
        """Extract RF from nodetool describering.

        Endpoint count in a token range = effective RF. Only nodetool needed,
        which is always available on Cassandra nodes.

        Returns:
            Tuple of (replication_factor, failure_reason).
        """
        dr_result = self.run_db_command(
            self.config.databases.cassandra,
            "nodetool describering brig",
        )

        output: str = dr_result.stdout.strip()
        if not output:
            return (None, "nodetool describering returned nothing")

        # Find the first endpoints:[...] block, all token ranges have same count
        endpoints_match: re.Match[str] | None = re.search(
            r"endpoints:\[([^\]]+)\]", output,
        )

        if not endpoints_match:
            return (None, "no endpoints block found")

        # Count comma-separated endpoints
        endpoints_str: str = endpoints_match.group(1).strip()
        endpoint_count: int = len([
            ep for ep in endpoints_str.split(",") if ep.strip()
        ])

        if endpoint_count == 0:
            return (None, "endpoints block is empty")

        return (endpoint_count, "")
