"""Count how many Kubernetes nodes are active.

Runs `kubectl get nodes -o json` and returns the length of the items array.
Returns 0 if no nodes are found.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class NodeCount(BaseTarget):
    """Count Kubernetes nodes in the cluster.

    Gets the full node list from the Kubernetes API and returns the total,
    including all nodes regardless of their Ready state.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Number of active Kubernetes nodes"

    @property
    def explanation(self) -> str:
        """Why we track this and what « healthy » means."""
        return (
            "Total node count matters because fewer nodes means less capacity. "
            "If you're below what you expect, pods might not schedule due to "
            "insufficient resources."
        )

    @property
    def unit(self) -> str:
        """Label for the value we return."""
        return "nodes"

    def collect(self) -> int:
        """Get the node list and return how many there are.

        Returns:
            How many nodes are registered in the cluster.

        Raises:
            RuntimeError: When kubectl fails or can't parse the output.
        """
        # Get all nodes as JSON so we can extract the items array reliably
        cmd_result, data = self.run_kubectl("nodes")

        # kubectl either failed or gave us garbage
        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        # Each node shows up as an entry in the items array
        items: list[Any] = data.get("items", [])
        count: int = len(items)

        # Summarize for the health report
        self._health_info = f"Kubernetes cluster has {count} node{'s' if count != 1 else ''}"

        return count
