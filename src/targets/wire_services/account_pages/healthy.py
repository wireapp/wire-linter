"""Account Pages health check target.

Checks whether all Account Pages pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
Account Pages serves the self-service account management UI, so downtime
directly affects end-user password resets and account operations.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class AccountPagesHealthy(BaseTarget):
    """Checks if Account Pages service is healthy.

    Queries Kubernetes for all Account Pages pods and verifies they are
    all in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Account Pages - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "If Account Pages pods are not running, users cannot reset passwords "
            "or manage their accounts through the self-service UI."
        )

    def collect(self) -> bool:
        """Check if all Account Pages pods are running and healthy.
        Returns True if at least one pod exists and all are Running + Ready."""
        # Show the operator which service we are currently querying
        self.terminal.step("Checking Account Pages pod status...")

        # Query pods for the account-pages service via kubectl
        cmd_result, pods = get_service_pods("account-pages", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Evaluate whether all returned pods are in a running and ready state
        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            # Include the actual running replica count in the description
            self._dynamic_description = f"Account Pages - {replica_label(running)}"

        # Optional: secondary health assessment (informational only)
        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
