"""Gundeck (push notifications) health check target.

Checks whether all Gundeck pods are running with all containers ready.
Uses kubectl to query pod status. Gundeck fans out push notifications to
mobile clients, so when it's unhealthy, users miss notifications on iOS
and Android.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class GundeckHealthy(BaseTarget):
    """Checks if Gundeck (push notifications) service is healthy.

    Queries Kubernetes for all Gundeck pods and verifies they're all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Gundeck (push notifications) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Gundeck fans out push notifications to mobile devices. Unhealthy pods "
            "cause missed notifications on iOS and Android, appearing as silent "
            "message loss."
        )

    def collect(self) -> bool:
        """Check if all Gundeck pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Gundeck pod status...")

        cmd_result, pods = get_service_pods("gundeck", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Gundeck (push notifications) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
