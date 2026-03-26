"""Grabs the Elasticsearch cluster health (green/yellow/red) from the _cluster/health API.

Hits the Elasticsearch REST endpoint via SSH, parses the JSON response back.
If that explodes, we fall back to the plain-text _cat/health output instead.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget
from src.lib.elasticsearch_helpers import build_es_auth_flag


class ElasticsearchClusterHealth(BaseTarget):
    """Checks if the Elasticsearch cluster is actually healthy.

    Connects over SSH, hits the REST API, and tells you if the cluster's
    sitting at green (good), yellow (missing replicas), or red (primary shards gone).
    """

    # Uses SSH to reach Elasticsearch nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Elasticsearch cluster health status"""
        return "Elasticsearch cluster health status"

    @property
    def explanation(self) -> str:
        """Green is all shards assigned. Yellow is missing replicas. Red is primary shards gone and data might be toast."""
        return (
            "Green means all shards are assigned. Yellow means replicas are missing. "
            "Red means primary shards are unassigned and data may be unavailable."
        )

    def collect(self) -> str:
        """Query the Elasticsearch cluster health and return the status colour.

        Returns:
            Health status string: "green", "yellow", "red", or "unknown".

        Raises:
            RuntimeError: If neither the JSON endpoint nor the _cat fallback
                returns a parseable response.
        """
        # Let the operator know what we're about to do
        self.terminal.step("Querying Elasticsearch cluster health...")

        # Grab the host once so we don't keep looking it up
        es_host: str = self.config.databases.elasticsearch

        # Build curl auth flag when ES credentials are configured (ES 8.x+ requires auth)
        es_auth: str = build_es_auth_flag(
            self.config.databases.elasticsearch_username,
            self.config.databases.elasticsearch_password,
        )

        # Hit the cluster health endpoint with curl
        result = self.run_db_command(
            es_host,
            f"curl -s {es_auth} 'http://localhost:9200/_cluster/health'",
        )

        # Bail early if curl itself failed (connection refused, timeout, DNS error)
        if not result.stdout.strip():
            raise RuntimeError(
                f"Elasticsearch health request failed (exit code {result.exit_code}): "
                f"{result.stderr[:200]}"
            )

        try:
            # Parse the JSON response, looking for the "status" field
            health: dict[str, str] = json.loads(result.stdout)
            status: str = health.get("status", "unknown")

            # Capture some extra details for the report
            node_count: str = str(health.get("number_of_nodes", "?"))
            self._health_info = f"Cluster '{health.get('cluster_name', '?')}': {status}, {node_count} nodes"

            return status
        except json.JSONDecodeError:
            # JSON parsing blew up maybe the node is still booting or returned garbage.
            # Fall back to the plain-text endpoint instead.
            result2 = self.run_db_command(
                es_host,
                f"curl -s {es_auth} 'http://localhost:9200/_cat/health'",
            )

            # _cat/health gives us space-separated fields: timestamp cluster-name status nodes ...
            # Status is the 4th field (index 3), cluster name is the 3rd field (index 2)
            # The output format varies by ES version (e.g. ES 2.x omits epoch/timestamp),
            # so we validate the parsed status and fall back to scanning all fields.
            valid_statuses: tuple[str, ...] = ("green", "yellow", "red")
            fields: list[str] = result2.stdout.strip().split()
            if len(fields) >= 4:
                # Populate _health_info the same way the primary path does so the report
                # has context even when JSON parsing failed
                cluster_name: str = fields[2]
                status: str = fields[3]

                # Verify the field at index 3 is actually a health status value
                if status in valid_statuses:
                    self._health_info = f"Cluster '{cluster_name}': {status}, ? nodes"
                    return status

            # Index 3 wasn't a valid status (unexpected format) scan all fields
            for field in fields:
                if field in valid_statuses:
                    self._health_info = f"Cluster '?': {field}, ? nodes"
                    return field

            raise RuntimeError("Could not determine Elasticsearch cluster health")
