"""Cargohold (asset storage) health check target.

Checks whether all Cargohold pods are running with all containers ready.
Uses kubectl to query pod status. Cargohold handles all file and media
uploads/downloads, so when it's down, users can't send images, videos, or attachments.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class CargoholdHealthy(BaseTarget):
    """Checks if Cargohold (asset storage) service is healthy.

    Queries Kubernetes for all Cargohold pods and verifies they're all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Cargohold (asset storage) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Cargohold handles all file and media uploads/downloads. Unhealthy pods "
            "prevent users from sending or receiving images, videos, and attachments."
        )

    def collect(self) -> bool:
        """Check if all Cargohold pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Cargohold pod status...")

        cmd_result, pods = get_service_pods("cargohold", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Cargohold (asset storage) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
