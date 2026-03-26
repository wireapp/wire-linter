"""Galley (conversations) health check target.

Checks whether all Galley pods are running with all containers ready.
Uses kubectl to query pod status. Galley manages conversation state, membership,
and message routing, so when it's down, users can't send or receive messages.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class GalleyHealthy(BaseTarget):
    """Checks if Galley (conversations) service is healthy.

    Queries Kubernetes for all Galley pods and verifies they're all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Galley (conversations) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Galley manages conversations, membership, and message routing. Unhealthy "
            "pods prevent users from sending messages or managing conversations."
        )

    @property
    def unit(self) -> str:
        """No units for a boolean health check."""
        return ""

    def collect(self) -> bool:
        """Check if all Galley pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Galley pod status...")

        cmd_result, pods = get_service_pods("galley", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Galley (conversations) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
