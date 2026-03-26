"""Checks if the asset host HTTP service is running.

If the asset host service is down, the webapp and the linter tool
itself may be unreachable. Tests the asset host on port 8080.

Topology-aware: uses config.nodes.assethost when set (for offline
deployments where the asset host is a separate VM), otherwise falls
back to localhost on the admin host.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class AssetHost(BaseTarget):
    """Checks if the asset host HTTP service is running.

    Curls the asset host on port 8080 to verify the service
    is responding.
    """

    # Uses SSH to admin host for curl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Asset host HTTP service running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "The asset host serves static files for the webapp. If it's down, "
            "the webapp may fail to load and the linter tool itself might become unreachable."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty since result is boolean)."""
        return ""

    def collect(self) -> bool:
        """Check if the asset host responds on port 8080.

        Uses config.nodes.assethost if set (the VM IP of a separate asset host).
        Otherwise falls back to localhost on the admin host.

        Returns:
            True if it responds, False otherwise.
        """
        # In offline deployments, the asset host is a separate VM with its own IP
        asset_host_ip: str = self.config.nodes.assethost
        if asset_host_ip:
            target_url: str = f"http://{asset_host_ip}:8080/"
            self.terminal.step(
                f"Checking asset host at {asset_host_ip}:8080 "
                f"(configured in nodes.assethost)..."
            )
        else:
            target_url = "http://localhost:8080/"
            self.terminal.step(
                f"Checking asset host at localhost:8080 on admin host..."
            )

        result = self.run_ssh(
            self.config.admin_host.ip,
            f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5"
            f" '{target_url}' 2>/dev/null",
        )

        status_code: str = result.stdout.strip()

        try:
            code: int = int(status_code)
        except ValueError:
            self._health_info = f"Could not reach asset host: {status_code}"
            return False

        responsive: bool = code > 0 and code < 500

        if responsive:
            self._health_info = f"Asset host responding (HTTP {code})"
        else:
            self._health_info = f"Asset host returned HTTP {code}"

        return responsive
