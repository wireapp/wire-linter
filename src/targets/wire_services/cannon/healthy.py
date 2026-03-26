"""Cannon (WebSocket push) health check target.

Checks whether all Cannon pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
Cannon maintains persistent WebSocket connections to clients; an
unhealthy Cannon causes real-time message delivery to fail silently.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class CannonHealthy(BaseTarget):
    """Checks if Cannon (WebSocket push) service is healthy.

    Queries Kubernetes for all Cannon pods and verifies they are all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Cannon (WebSocket push) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Cannon maintains persistent WebSocket connections for real-time message "
            "push. Unhealthy pods cause silent message delivery failures for "
            "connected clients."
        )

    def collect(self) -> bool:
        """Check if all Cannon pods are running and healthy.
        Returns True if at least one pod exists and all are Running + Ready."""
        # Show the operator which service we are currently querying
        self.terminal.step("Checking Cannon pod status...")

        # Query pods for the cannon service using the shared helper
        cmd_result, pods = get_service_pods("cannon", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Evaluate whether all returned pods are in a running and ready state
        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            # Include the actual running replica count in the description
            self._dynamic_description = f"Cannon (WebSocket push) - {replica_label(running)}"

        # Optional: secondary health assessment (informational only)
        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
