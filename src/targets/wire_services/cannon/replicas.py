"""Cannon (WebSocket push) replica count target.

Counts the number of running Cannon pod replicas via kubectl.
We track this separately from health to catch scale-down events
even when the remaining pods are healthy.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods


class CannonReplicas(BaseTarget):
    """Counts running Cannon pod replicas.

    Queries Kubernetes for Cannon pods and returns how many are in the
    Running phase.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Number of Cannon pod replicas"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Fewer Cannon replicas means reduced WebSocket capacity. Each lost "
            "replica disconnects its connected clients, causing message delivery gaps."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement for the replica count value."""
        return "pods"

    def collect(self) -> int:
        """Count running Cannon pod replicas.

        Returns:
            Integer count of Cannon pods in Running phase.
        """
        self.terminal.step("Counting Cannon replicas...")

        cmd_result, pods = get_service_pods("cannon", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Tally only pods that are in Running phase
        count: int = count_replicas(pods)

        # Summarize for the health report
        self._health_info = f"cannon running {count} replica pod{'s' if count != 1 else ''}"

        return count
