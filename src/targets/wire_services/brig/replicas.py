"""Brig (user accounts) replica count target.

Counts the number of running Brig pod replicas via kubectl.
Tracking the replica count separately from health allows operators
to detect scale-down events even when remaining pods are healthy.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods


class BrigReplicas(BaseTarget):
    """Counts the number of running Brig pod replicas.

    Queries Kubernetes for Brig pods and returns the count of those
    currently in the Running phase.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Number of Brig pod replicas"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Fewer Brig replicas than expected means reduced capacity for user "
            "operations. A drop to zero means complete authentication outage."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement for the replica count value."""
        return "pods"

    def collect(self) -> int:
        """Count the number of currently running Brig pod replicas.
        Returns the integer count of Brig pods in Running phase."""
        # Show the operator which service we are currently querying
        self.terminal.step("Counting Brig replicas...")

        # Query pods for the brig service using the shared helper
        cmd_result, pods = get_service_pods("brig", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Tally only pods that are in Running phase, ignoring Pending/Failed/Unknown
        count: int = count_replicas(pods)

        # Summarize for the health report
        self._health_info = f"brig running {count} replica pod{'s' if count != 1 else ''}"

        return count
