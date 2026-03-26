"""Counts how many buckets exist in MinIO via mc admin info.

Grabs the bucket count from mc admin info output to verify the setup
actually has storage buckets configured.
"""

from __future__ import annotations

# External
import json
import re

# Ours
from src.lib.base_target import BaseTarget


class MinioBucketCount(BaseTarget):
    """Checks how many buckets MinIO has.

    Connects to the MinIO host over SSH and extracts the bucket count
    from mc admin info output.
    """

    # Uses SSH to reach MinIO nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What the check is called."""
        return "MinIO bucket count"

    @property
    def explanation(self) -> str:
        """Why we care and what goes wrong if it fails."""
        return (
            "Verifies that expected storage buckets exist. Zero buckets after a fresh "
            "install means asset storage is not set up and file uploads will fail."
        )

    @property
    def unit(self) -> str:
        """What label goes next to the number."""
        return "buckets"

    def collect(self) -> int:
        """Count MinIO buckets from mc admin info.

        Returns:
            Number of buckets.

        Raises:
            RuntimeError: If bucket count cannot be determined.
        """
        self.terminal.step("Counting MinIO buckets...")

        result = self.run_db_command(
            self.config.databases.minio,
            "sudo mc admin info local --json 2>/dev/null"
            " || sudo mc admin info myminio --json 2>/dev/null"
            " || sudo mc admin info local 2>/dev/null"
            " || sudo mc admin info myminio 2>/dev/null",
        )

        output: str = result.stdout.strip()

        # Try JSON first since it's structured mc produces NDJSON (one object per line per server)
        for line in output.split("\n"):
            line = line.strip()

            # Skip blank lines and non-JSON lines
            if not line or not line.startswith("{"):
                continue

            try:
                info: dict = json.loads(line)
                count: int | None = info.get("info", {}).get("buckets", {}).get("count")
                if count is not None:
                    # 0 is a valid result just means no uploads will work
                    self._health_info = f"{count} bucket(s)"
                    return int(count)
            except json.JSONDecodeError:
                continue

        # Fall back to regex look for "X Buckets" or "Buckets: X"
        match = re.search(r"(\d+)\s+[Bb]uckets?", output)
        if match:
            regex_count: int = int(match.group(1))
            self._health_info = f"{regex_count} bucket(s)"
            return regex_count

        match2 = re.search(r"[Bb]uckets?:\s*(\d+)", output)
        if match2:
            regex_count = int(match2.group(1))
            self._health_info = f"{regex_count} bucket(s)"
            return regex_count

        raise RuntimeError("Could not determine MinIO bucket count")
