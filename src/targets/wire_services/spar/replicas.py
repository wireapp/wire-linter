"""Spar (SSO/SCIM) replica count.

Tracks how many Spar pods are running. Separate from health checks,
so we can catch scale-down events even if the remaining pods are fine."""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods


class SparReplicas(BaseTarget):
    """Counts the number of running Spar pod replicas."""

    @property
    def description(self) -> str:
        return "Number of Spar pod replicas"

    @property
    def explanation(self) -> str:
        return (
            "Fewer replicas means less SSO capacity. When load picks up, "
            "enterprise users will hit login failures."
        )

    @property
    def unit(self) -> str:
        return "pods"

    def collect(self) -> int:
        """Count the number of currently running Spar pod replicas."""
        self.terminal.step("Counting Spar replicas...")

        cmd_result, pods = get_service_pods("spar", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        # Tally only pods that are in Running phase
        count: int = count_replicas(pods)

        # Summarize for the health report
        self._health_info = f"spar running {count} replica pod{'s' if count != 1 else ''}"

        return count
