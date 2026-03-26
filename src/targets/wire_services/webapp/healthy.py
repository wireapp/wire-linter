"""Webapp health check target.

Checks whether all Webapp pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
The Webapp is the main browser-based Wire client; its unavailability
prevents users from accessing Wire through a web browser.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class WebappHealthy(BaseTarget):
    """Checks if Webapp service is healthy.

    Queries Kubernetes for all Webapp pods and verifies they are all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Webapp - all replicas running"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "The Webapp is the main browser-based Wire client. If pods are down, "
            "users can't access Wire from their browser."
        )

    def collect(self) -> bool:
        """Check if all Webapp pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Webapp pod status...")

        cmd_result, pods = get_service_pods("webapp", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Webapp - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
