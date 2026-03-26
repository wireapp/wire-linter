"""MinIO erasure set health check makes sure the cluster can still accept writes.

MinIO needs N/2+1 nodes to stay in read-write mode. Lose too many and it falls back
to read-only, which means users can't upload files, avatars, or anything else.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget


class MinioErasureHealth(BaseTarget):
    """Checks if MinIO is still in read-write mode or if it's degraded.

    Parses mc admin info output to figure out whether the cluster is healthy
    or stuck in read-only because too many nodes are down.
    """

    # Uses SSH to reach MinIO nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Is MinIO healthy enough to accept writes?"""
        return "MinIO erasure set health (read-write mode)"

    @property
    def explanation(self) -> str:
        """MinIO needs quorum to stay operational.

        Without N/2+1 nodes, it drops to read-only and users can't upload anything.
        """
        return (
            "MinIO needs N/2+1 nodes for read-write quorum. Below that it enters "
            "read-only mode and users cannot upload files, avatars, or assets."
        )

    def collect(self) -> str:
        """Grab MinIO status and check if it's still writable.

        Returns:
            "read-write" if cluster is fully operational,
            "read-only" or "degraded" if quorum is at risk.

        Raises:
            RuntimeError: If status cannot be determined.
        """
        self.terminal.step("Checking MinIO erasure set health...")

        result = self.run_db_command(
            self.config.databases.minio,
            "sudo mc admin info local 2>/dev/null"
            " || sudo mc admin info myminio 2>/dev/null",
        )

        output: str = result.stdout.strip().lower()

        # Look for explicit status in output
        if "read-write" in output or "online" in output:
            # Try to pull drive counts
            drives_match = re.search(r"(\d+)\s+drives?\s+online.*?(\d+)\s+drives?\s+offline", output)
            if drives_match:
                online: int = int(drives_match.group(1))
                offline: int = int(drives_match.group(2))
                if offline == 0:
                    self._health_info = f"Read-write, {online} drives online, 0 offline"
                    return "read-write"
                else:
                    self._health_info = f"Degraded: {online} online, {offline} offline"
                    return "degraded"

            # Newer MinIO format uses "Drives: X/Y OK"
            ok_match = re.search(r"drives:\s*(\d+)/(\d+)\s*ok", output)
            if ok_match:
                ok_count: int = int(ok_match.group(1))
                total: int = int(ok_match.group(2))
                if ok_count == total:
                    self._health_info = f"Read-write, {ok_count}/{total} drives OK"
                    return "read-write"
                else:
                    self._health_info = f"Degraded: {ok_count}/{total} drives OK"
                    return "degraded"

            self._health_info = "Read-write mode detected"
            return "read-write"

        if "read-only" in output:
            self._health_info = "CRITICAL: MinIO is in read-only mode"
            return "read-only"

        # Couldn't parse anything raise so the check appears as a failure
        raise RuntimeError(f"Could not determine MinIO erasure health: {output[:80]}")
