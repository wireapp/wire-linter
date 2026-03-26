"""Grabs the MinIO server version from mc admin info.

We need to know what version is running for compatibility checks and support."""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget


class MinioVersion(BaseTarget):
    """Pulls the MinIO server version via SSH.

    Connects to MinIO, runs mc admin info, and extracts the version string
    from whatever format mc decided to spit out today.
    """

    # Uses SSH to reach MinIO nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target is checking."""
        return "MinIO server version"

    @property
    def explanation(self) -> str:
        """Why we care about MinIO version."""
        return (
            "Tracks the MinIO version so we know if it's got security patches "
            "and features Wire actually needs to run."
        )

    def collect(self) -> str:
        """Get MinIO version from mc admin info.

        Returns:
            MinIO version string.

        Raises:
            RuntimeError: If version cannot be determined.
        """
        self.terminal.step("Checking MinIO version...")

        result = self.run_db_command(
            self.config.databases.minio,
            "sudo mc admin info local 2>/dev/null"
            " || sudo mc admin info myminio 2>/dev/null",
        )

        output: str = result.stdout.strip()

        # Try the standard release tag format first
        # Format looks like RELEASE.2023-07-21T21-12-44Z
        match = re.search(r"(RELEASE\.\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)", output)
        if match:
            version: str = match.group(1)
            self._health_info = version
            return version

        # Fallback to generic Version: pattern
        match2 = re.search(r"[Vv]ersion[:\s]+(\S+)", output)
        if match2:
            version = match2.group(1)
            self._health_info = version
            return version

        # Grab first non-empty line if we're stuck
        for line in output.split("\n"):
            if line.strip():
                self._health_info = line.strip()[:80]
                return line.strip()

        raise RuntimeError("Could not determine MinIO version")
