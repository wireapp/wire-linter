"""Brig (user accounts) health check target.

Checks whether all Brig pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
Brig is the core user-management service; its unavailability prevents
logins, registrations, and any operation that requires identity lookup.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class BrigHealthy(BaseTarget):
    """Checks if Brig (user accounts) service is healthy.

    Queries Kubernetes for all Brig pods and verifies they are all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Brig (user accounts) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Brig is the core user-management service. If any pod is not ready, "
            "logins, registrations, and identity lookups fail for a portion of traffic."
        )

    def collect(self) -> bool:
        """Check if all Brig pods are running and healthy.
        Returns True if at least one pod exists and all are Running + Ready."""
        # Show the operator which service we are currently querying
        self.terminal.step("Checking Brig pod status...")

        # Query pods for the brig service using the shared helper
        cmd_result, pods = get_service_pods("brig", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Evaluate whether all returned pods are in a running and ready state
        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Brig (user accounts) - {replica_label(running)}"

        # Optional: secondary health assessment (informational only)
        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
