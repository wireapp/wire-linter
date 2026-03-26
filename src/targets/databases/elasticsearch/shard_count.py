"""Grabs the active shard count from Elasticsearch cluster health.

Just hits the _cluster/health endpoint and pulls out the active_shards number.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget
from src.lib.elasticsearch_helpers import build_es_auth_flag


class ElasticsearchShardCount(BaseTarget):
    """Gets the count of active shards in the Elasticsearch cluster.

    Pings the _cluster/health REST API and extracts active_shards.
    """

    # Uses SSH to reach Elasticsearch nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target checks human readable."""
        return "Elasticsearch active shard count"

    @property
    def explanation(self) -> str:
        """Watches shard count unassigned or relocating shards mean cluster trouble."""
        return (
            "Tracks the number of active shards. Unassigned or relocating shards "
            "indicate cluster instability or recent node loss."
        )

    @property
    def unit(self) -> str:
        """What we're counting."""
        return "shards"

    def collect(self) -> int:
        """Count active shards from the cluster health API.

        Returns:
            Number of active shards in the cluster.

        Raises:
            RuntimeError: If the cluster health API cannot be queried.
        """
        self.terminal.step("Counting Elasticsearch shards...")

        es_host: str = self.config.databases.elasticsearch

        # Build curl auth flag when ES credentials are configured (ES 8.x+ requires auth)
        es_auth: str = build_es_auth_flag(
            self.config.databases.elasticsearch_username,
            self.config.databases.elasticsearch_password,
        )

        # Call curl on the host to get cluster health
        result = self.run_db_command(
            es_host,
            f"curl -s {es_auth} 'http://localhost:9200/_cluster/health'",
        )

        # Bail early if the SSH command failed (wrong credentials, unreachable host, etc.)
        if not result.success:
            raise RuntimeError(
                f"Elasticsearch health request failed (exit code {result.exit_code}): "
                f"{result.stderr[:200] if result.stderr.strip() else result.stdout[:200]}"
            )

        # Bail early if curl itself returned nothing (connection refused, timeout)
        if not result.stdout.strip():
            raise RuntimeError(
                f"Elasticsearch health request returned empty output (exit code {result.exit_code}): "
                f"{result.stderr[:200]}"
            )

        try:
            health: dict = json.loads(result.stdout)
            active: int = health.get("active_shards", 0)
            unassigned: int = health.get("unassigned_shards", 0)
            relocating: int = health.get("relocating_shards", 0)

            # Build a status line showing what's happening with shards
            if unassigned > 0:
                self._health_info = f"{active} active, {unassigned} unassigned"
            elif relocating > 0:
                self._health_info = f"{active} active, {relocating} relocating"
            else:
                self._health_info = f"{active} active shards, all assigned"

            return active
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Could not parse Elasticsearch cluster health JSON (exit code {result.exit_code}): "
                f"{result.stdout[:200]}"
            )
