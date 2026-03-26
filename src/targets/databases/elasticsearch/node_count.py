"""Counts Elasticsearch nodes by hitting the _cluster/health REST API.

Grabs the number_of_nodes field from the health endpoint. If that doesn't work,
counts up the lines from _cat/nodes instead.
"""

from __future__ import annotations

# External
import json
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.elasticsearch_helpers import build_es_auth_flag


class ElasticsearchNodeCount(BaseTarget):
    """Checks how many nodes you've got in your Elasticsearch cluster.

    Connects to the host via SSH and pokes the REST API to find out
    how many nodes are actually online.
    """

    # Uses SSH to reach Elasticsearch nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What we're checking: the node count."""
        return "Number of Elasticsearch nodes"

    @property
    def explanation(self) -> str:
        """Node count matters if you're missing nodes, you've got problems."""
        return (
            "Tracks the number of nodes in the Elasticsearch cluster. Fewer nodes than "
            "expected means a node is down, risking search outages or data loss."
        )

    @property
    def unit(self) -> str:
        """Measured in nodes."""
        return "nodes"

    def collect(self) -> int:
        """Count the number of nodes in the Elasticsearch cluster.

        Returns:
            Integer count of nodes reported by the cluster health API,
            or the number of non-empty lines from _cat/nodes as fallback.

        Raises:
            RuntimeError: If neither source can be parsed.
        """
        # Let the user know we're doing this
        self.terminal.step("Counting Elasticsearch nodes...")

        # Pull the host config once so we don't look it up twice
        es_host: str = self.config.databases.elasticsearch

        # Build curl auth flag when ES credentials are configured (ES 8.x+ requires auth)
        es_auth: str = build_es_auth_flag(
            self.config.databases.elasticsearch_username,
            self.config.databases.elasticsearch_password,
        )

        # Hit the cluster health endpoint, nice and simple
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
            # Parse the JSON and grab the node count
            health: dict[str, int] = json.loads(result.stdout)
            count: int = health.get("number_of_nodes", 0)

            # Summarize what we found for the health report
            self._health_info = f"Elasticsearch cluster has {count} node{'s' if count != 1 else ''}"

            return count
        except json.JSONDecodeError:
            # JSON didn't work fall back to _cat/nodes and count the rows.
            # Each line is a node, empty lines don't count.
            result2 = self.run_db_command(
                es_host,
                f"curl -s {es_auth} 'http://localhost:9200/_cat/nodes'",
            )

            # _cat/nodes lines start with an IP address (e.g. "10.0.0.1 65 97 ...").
            # Only count lines that match this format so error messages or
            # authentication failures don't get mistaken for node entries.
            ip_pattern: re.Pattern[str] = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
            lines: list[str] = [
                line for line in result2.stdout.strip().split("\n")
                if line.strip() and ip_pattern.match(line.strip())
            ]
            fallback_count: int = len(lines)

            # If no valid node lines were found, we genuinely failed to determine
            # the count — don't silently return 0 as if the cluster has no nodes
            if fallback_count == 0:
                raise RuntimeError("Could not determine Elasticsearch node count")

            # Summarize what we found for the health report
            self._health_info = f"Elasticsearch cluster has {fallback_count} node{'s' if fallback_count != 1 else ''}"

            return fallback_count
