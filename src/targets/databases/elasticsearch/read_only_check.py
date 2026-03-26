"""Checks if Elasticsearch got stuck in read-only mode when the disk filled up.

Elasticsearch auto-locks itself as read-only when disk space hits the watermark,
and search/indexing just silently stops. This checks the index.blocks.read_only_allow_delete
setting across all indices to catch that happening.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget
from src.lib.elasticsearch_helpers import build_es_auth_flag


class ElasticsearchReadOnlyCheck(BaseTarget):
    """Checks if Elasticsearch has frozen any indices due to read-only mode.

    Hits the _settings endpoint and looks for the index.blocks.read_only_allow_delete
    flag set to "true" that's the telltale sign something went wrong.
    """

    # Uses SSH to reach Elasticsearch nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Quick summary: Elasticsearch isn't locked in read-only."""
        return "Elasticsearch not in read-only mode"

    @property
    def explanation(self) -> str:
        """The problem: disk fills, Elasticsearch locks itself, everything stops working. Healthy = no frozen indices."""
        return (
            "When disk fills past the watermark, Elasticsearch goes read-only and "
            "search/indexing silently stops. Healthy when no indices have the "
            "read_only_allow_delete block set."
        )

    @property
    def unit(self) -> str:
        """No units for a yes/no check."""
        return ""

    def collect(self) -> bool:
        """Check if any indices are stuck in read-only mode.

        Returns:
            True if no indices are read-only, False if any are blocked.

        Raises:
            RuntimeError: If the settings endpoint cannot be queried.
        """
        self.terminal.step("Checking Elasticsearch read-only status...")

        es_host: str = self.config.databases.elasticsearch

        # Build curl auth flag when ES credentials are configured (ES 8.x+ requires auth)
        es_auth: str = build_es_auth_flag(
            self.config.databases.elasticsearch_username,
            self.config.databases.elasticsearch_password,
        )

        # Grab all index settings with flat=true so the nested keys come out as dot notation
        result = self.run_db_command(
            es_host,
            f"curl -s {es_auth} 'http://localhost:9200/_all/_settings?flat_settings=true'",
        )

        # Bail early if the SSH command itself failed before even looking at output
        if not result.success:
            raise RuntimeError(f"SSH command failed: {result.stderr}")

        # Bail early if curl itself failed (connection refused, timeout, DNS error)
        if not result.stdout.strip():
            raise RuntimeError(
                f"Elasticsearch settings request failed (exit code {result.exit_code}): "
                f"{result.stderr[:200]}"
            )

        try:
            settings: dict = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Could not parse Elasticsearch settings response (exit code {result.exit_code}): "
                f"{result.stdout[:200]}"
            )

        # ES error responses are valid JSON but contain an "error" key instead of index data
        if "error" in settings:
            error_type: str = ""
            if isinstance(settings["error"], dict):
                error_type = settings["error"].get("type", "unknown")
            raise RuntimeError(
                f"Elasticsearch returned an error response: {error_type}"
            )

        # Walk through each index and hunt for the read_only_allow_delete flag
        read_only_indices: list[str] = []
        checked_count: int = 0

        for index_name, index_data in settings.items():
            # Skip entries that aren't proper index objects (safety against unexpected shapes)
            if not isinstance(index_data, dict) or "settings" not in index_data:
                self.terminal.warning(
                    f"Skipping unexpected entry '{index_name}' in settings response"
                )
                continue

            checked_count += 1
            flat_settings: dict = index_data.get("settings", {})
            # Can show up flat or nested, but we asked for flat above
            ro_flag: str = flat_settings.get(
                "index.blocks.read_only_allow_delete", "false"
            )
            if ro_flag == "true":
                read_only_indices.append(index_name)

        not_read_only: bool = len(read_only_indices) == 0

        if not_read_only:
            self._health_info = f"No indices in read-only mode ({checked_count} indices checked)"
        else:
            self._health_info = (
                f"{len(read_only_indices)} indices in read-only mode: "
                f"{', '.join(read_only_indices[:5])}"
            )

        return not_read_only
