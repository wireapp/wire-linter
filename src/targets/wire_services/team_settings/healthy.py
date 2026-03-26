"""Team Settings health check target.

Checks whether all Team Settings pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
Team Settings serves the web UI for team administrators to manage members,
permissions, and billing; its unavailability blocks admin operations.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class TeamSettingsHealthy(BaseTarget):
    """Checks if Team Settings service is healthy.

    Queries Kubernetes for all Team Settings pods and verifies they are
    all in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Team Settings - all replicas running"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "Team Settings handles the admin UI for managing team members and "
            "permissions. If pods are down, admins can't do any team management."
        )

    def collect(self) -> bool:
        """Check if all Team Settings pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Team Settings pod status...")

        cmd_result, pods = get_service_pods("team-settings", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Team Settings - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
