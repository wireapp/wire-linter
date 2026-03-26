"""Nginz (API gateway) health check target.

Checks whether all Nginz pods are running with all containers ready.
Uses kubectl to query pod status. Nginz is the nginx-based reverse proxy
that fronts all Wire API traffic, so when it's down, the entire Wire API
is unreachable from clients.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class NginzHealthy(BaseTarget):
    """Checks if Nginz (API gateway) service is healthy.

    Queries Kubernetes for all Nginz pods and verifies they're all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Nginz (API gateway) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Nginz is the API gateway fronting all Wire traffic. If any pod is "
            "unhealthy, a portion of client requests fail with connection errors."
        )

    def collect(self) -> bool:
        """Check if all Nginz pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Nginz pod status...")

        cmd_result, pods = get_service_pods("nginz", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Nginz (API gateway) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
