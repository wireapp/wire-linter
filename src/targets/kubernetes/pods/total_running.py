"""Count total running pods across all namespaces.

Queries all pods and counts those in the «Running» phase.
Complement to unhealthy pod counts.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class TotalRunning(BaseTarget):
    """Count running pods across all namespaces.

    Iterates through all pods in the cluster, counting those in the
    «Running» phase.
    """

    @property
    def description(self) -> str:
        return "Total running pods"

    @property
    def explanation(self) -> str:
        return (
            "Baseline for running pods. Big drop means workloads aren't starting or are getting evicted."
        )

    @property
    def unit(self) -> str:
        return "pods"

    def collect(self) -> int:
        """Fetch all pods and count those in Running phase.

        Returns:
            Count of running pods.

        Raises:
            RuntimeError: On kubectl failure.
        """
        cmd_result, data = self.run_kubectl("pods", all_namespaces=True)

        if data is None:
            raise RuntimeError("Failed to get pods from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])
        running: int = 0

        for pod in items:
            # phase is the authoritative lifecycle state
            phase: str = pod.get("status", {}).get("phase", "")

            if phase == "Running":
                running += 1

        # Summarize for the health report
        self._health_info = f"{running} pod{'s' if running != 1 else ''} in Running state across all namespaces"

        return running
