"""Background Worker health check target.

Checks whether all Background Worker pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
The Background Worker handles async tasks such as email sending and
push notification processing, so its health directly affects
reliability of user-facing notifications.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class BackgroundWorkerHealthy(BaseTarget):
    """Checks if Background Worker service is healthy.

    Queries Kubernetes for all Background Worker pods and verifies they
    are all in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Background Worker - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "The Background Worker processes async tasks like email delivery and "
            "push notifications. Unhealthy workers cause silent failures in "
            "user-facing notifications."
        )

    def collect(self) -> bool:
        """Check if all Background Worker pods are running and healthy.
        Returns True if at least one pod exists and all are Running + Ready."""
        # Show the operator which service we are currently querying
        self.terminal.step("Checking Background Worker pod status...")

        # Use hyphenated name matching the Kubernetes pod naming convention
        cmd_result, pods = get_service_pods("background-worker", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Evaluate whether all returned pods are in a running and ready state
        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            # Include the actual running replica count in the description
            self._dynamic_description = f"Background Worker - {replica_label(running)}"

        # Optional: secondary health assessment (informational only)
        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
