"""Checks MinIO drive health by parsing mc admin info output.

Looks for drive online/offline counts in the mc admin info text. MinIO changed
the output format over versions older ones say « X drives online, Y drives offline »,
newer ones say « Drives: X/Y OK ». We try 'local' alias first, then fall back to 'myminio'.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget


class MinioDrivesStatus(BaseTarget):
    """Checks if MinIO drives are healthy.

    Runs mc admin info on the MinIO host via SSH and extracts drive counts
    from the output. Different mc versions format this differently, so we
    handle both old and new styles.
    """

    # Uses SSH to reach MinIO nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """MinIO drives are online and functioning."""
        return "MinIO drives health"

    @property
    def explanation(self) -> str:
        """Offline drives mess with redundancy and can trigger read-only mode. Need all drives reporting online."""
        return (
            "Offline drives reduce redundancy and can push the cluster into "
            "read-only mode. Healthy when all drives report online/OK."
        )

    def collect(self) -> str:
        """Check MinIO drives health and return a summary string.

        Returns:
            "X/Y online" for the older output format, or "X/Y OK" for the newer format.

        Raises:
            RuntimeError: If neither output pattern can be matched.
        """
        # Tell the operator we're checking
        self.terminal.step("Checking MinIO drives...")

        # Try 'local' alias first since it's more common, then 'myminio' as fallback.
        # mc config lives in root's home, so we need sudo.
        result = self.run_db_command(
            self.config.databases.minio,
            "sudo mc admin info local 2>/dev/null || sudo mc admin info myminio 2>/dev/null",
        )

        # Old mc format: "X drives online, Y drives offline"
        match = re.search(r"(\d+)\s+drives?\s+online.*?(\d+)\s+drives?\s+offline", result.stdout)
        if match:
            # Calculate total from the two numbers we found
            online: int = int(match.group(1))
            offline: int = int(match.group(2))
            total: int = online + offline

            # Summarize drive health for the report
            self._health_info = f"MinIO drives: {online}/{total} online, {offline} offline"

            return f"{online}/{total} online"

        # New mc format: "Drives: X/Y OK" just grab the fraction
        match2 = re.search(r"Drives:\s*(\d+/\d+\s*OK)", result.stdout)
        if match2:
            status: str = match2.group(1)

            # Summarize drive health for the report
            self._health_info = f"MinIO drives: {status}"

            return status

        raise RuntimeError("Could not determine MinIO drives status")
