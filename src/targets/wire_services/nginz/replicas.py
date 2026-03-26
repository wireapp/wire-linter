"""Nginz (API gateway) replica count target.

Counts the number of running Nginz pod replicas via kubectl.
Tracking the replica count separately from health allows operators
to detect scale-down events even when remaining pods are healthy.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods


class NginzReplicas(BaseTarget):
    """Counts the number of running Nginz pod replicas.

    Queries Kubernetes for Nginz pods and returns the count of those
    currently in the Running phase.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Number of Nginz pod replicas"

    @property
    def explanation(self) -> str:
        """Why this matters fewer replicas means less API gateway capacity, and zero makes the entire API unreachable."""
        return (
            "Fewer Nginz replicas reduces API gateway capacity. A drop to zero "
            "makes the entire Wire API unreachable from all clients."
        )

    @property
    def unit(self) -> str:
        """We measure this in pods."""
        return "pods"

    def collect(self) -> int:
        """Count how many Nginz pod replicas are currently running."""
        # Let the operator know what we're querying
        self.terminal.step("Counting Nginz replicas...")

        # Get the pods for the nginz service
        cmd_result, pods = get_service_pods("nginz", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Count only Running pods
        count: int = count_replicas(pods)

        # Summarize for the health report
        self._health_info = f"nginz running {count} replica pod{'s' if count != 1 else ''}"

        return count
