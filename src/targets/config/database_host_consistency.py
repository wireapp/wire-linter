"""Checks database hosts are consistent across all Wire services.

One mismatch and a service talks to the wrong database. Extracts Cassandra,
PostgreSQL, Elasticsearch, Redis hosts from all service ConfigMaps.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


# Services that need consistent DB hosts
_SERVICES: list[str] = ["brig", "galley", "gundeck", "spar", "background-worker"]

# Config paths where DB hosts appear (db_type, candidate_paths)
_DB_HOST_PATHS: list[tuple[str, list[str]]] = [
    ("cassandra",      ["cassandra.host", "cassandra.hosts"]),
    ("elasticsearch",  ["elasticsearch.url", "elasticsearch.host"]),
    ("postgresql",     ["postgresql-config.host", "postgreSQL.host"]),
    ("redis",          ["redis.host", "redis.writeEndpoint.host"]),
]


class DatabaseHostConsistency(BaseTarget):
    """Checks DB host consistency across Wire services.

    Fetches ConfigMaps and verifies all services reference the same DB hosts.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Database host consistency across Wire services"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "If one service points to a different DB host, it reads/writes wrong data. "
            "Healthy when all services agree on Cassandra, PostgreSQL, "
            "Elasticsearch, and Redis."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check DB host consistency across services.

        Returns:
            True if all consistent, False otherwise.
        """
        self.terminal.step("Checking database host consistency...")

        # Collect DB host refs: {db_type: {service: frozenset of host strings}}
        # frozenset ensures list values (e.g. cassandra.hosts) compare order-independently
        db_refs: dict[str, dict[str, frozenset[str]]] = {}

        for svc in _SERVICES:
            _result, cm_data = self.run_kubectl(f"configmap/{svc}")

            if not isinstance(cm_data, dict):
                continue

            data_section: dict[str, str] = cm_data.get("data", {})
            yaml_key: str = f"{svc}.yaml"
            yaml_content: str = data_section.get(yaml_key, "")

            if not yaml_content:
                # Look for any .yaml/.yml key
                for key in data_section:
                    if key.endswith(".yaml") or key.endswith(".yml"):
                        yaml_content = data_section[key]
                        break

            if not yaml_content:
                continue

            try:
                config: dict[str, Any] = parse_yaml(yaml_content)
            except (ValueError, TypeError):
                continue

            # Extract DB host refs
            for db_type, paths in _DB_HOST_PATHS:
                for path in paths:
                    value: Any = get_nested(config, path)
                    if value:
                        if db_type not in db_refs:
                            db_refs[db_type] = {}
                        # Normalise to frozenset so list-valued paths (e.g.
                        # cassandra.hosts) compare by membership, not order
                        normalised: frozenset[str] = (
                            frozenset(str(v) for v in value)
                            if isinstance(value, list)
                            else frozenset({str(value)})
                        )
                        db_refs[db_type][svc] = normalised
                        break

        if not db_refs:
            raise RuntimeError(
                "No DB host refs found: all service ConfigMap fetches failed"
            )

        # Check consistency per DB type
        inconsistencies: list[str] = []

        for db_type, service_hosts in db_refs.items():
            unique_hosts: set[frozenset[str]] = set(service_hosts.values())
            if len(unique_hosts) > 1:
                detail: str = ", ".join(
                    # Sort hosts within each frozenset for deterministic display
                    f"{svc}={', '.join(sorted(hosts))}"
                    for svc, hosts in service_hosts.items()
                )
                inconsistencies.append(f"{db_type}: {detail}")

        consistent: bool = len(inconsistencies) == 0

        if consistent:
            db_count: int = len(db_refs)
            self._health_info = f"All services consistent across {db_count} DB type(s)"
        else:
            self._health_info = f"Inconsistencies: {'; '.join(inconsistencies)}"

        return consistent
