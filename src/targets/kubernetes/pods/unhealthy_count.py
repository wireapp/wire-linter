"""Counts pods not in Running or Completed state.

Queries all pods across all namespaces and counts those whose phase
is not Running or Succeeded. Uses «Succeeded» (the K8s phase name)
rather than «Completed».
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class UnhealthyCount(BaseTarget):
    """Counts pods not in Running or Completed state.

    Walks through every pod in the cluster and increments the counter for
    each one that's neither Running nor Succeeded.
    """

    @property
    def description(self) -> str:
        """Brief description of what we're checking."""
        return "Number of pods not in Running or Completed state"

    @property
    def explanation(self) -> str:
        """Why this matters and when things are healthy."""
        return (
            "Pods stuck in Pending, Failed, or Unknown aren't serving traffic. "
            "Healthy means zero pods outside Running or Succeeded."
        )

    @property
    def unit(self) -> str:
        """What unit we're counting."""
        return "pods"

    def collect(self) -> int:
        """Fetch all pods and count the unhealthy ones.

        Returns:
            Count of pods not in Running or Succeeded phase.

        Raises:
            RuntimeError: If kubectl fails to return pod data.
        """
        # Get all pods across all namespaces
        cmd_result, data = self.run_kubectl("pods", all_namespaces=True)

        # If kubectl failed or gave us garbage, bail
        if data is None:
            raise RuntimeError("Failed to get pods from kubectl")

        # Pull the items array
        items: list[dict[str, Any]] = data.get("items", [])

        unhealthy: int = 0

        for pod in items:
            # Phase is the actual state of the pod
            phase: str = pod.get("status", {}).get("phase", "")

            # Running and Succeeded are the only healthy states
            if phase not in ("Running", "Succeeded"):
                unhealthy += 1

        # Summarize for the health report
        if unhealthy == 0:
            self._health_info = "No unhealthy pods detected"
        else:
            self._health_info = f"{unhealthy} pod{'s' if unhealthy != 1 else ''} in non-Running state"

        return unhealthy
