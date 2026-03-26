"""Check if all Kubernetes nodes are in Ready state.

Runs kubectl get nodes -o json and looks at the conditions array in
each node's status. We're checking that every single node has Ready=True.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class AllReady(BaseTarget):
    """Check if all Kubernetes nodes are ready.

    Loop through all nodes and verify each one has Ready=True. Just one
    non-ready node and we return False.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "All Kubernetes nodes are in Ready state"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "NotReady nodes can't schedule pods. Workloads on those nodes get evicted "
            "or stuck. If every node has Ready=True, we're healthy."
        )

    @property
    def unit(self) -> str:
        """We're returning a bool, so no unit."""
        return ""

    def collect(self) -> bool:
        """Check every node has Ready=True.

        Returns:
            True if all nodes are ready, False if any aren't.

        Raises:
            RuntimeError: If kubectl fails.
        """
        # Get nodes as JSON we need it structured for reliable access
        cmd_result, data = self.run_kubectl("nodes")

        # If data is None, kubectl either failed or gave us garbage
        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        # Pull out the list of node objects
        items: list[dict[str, Any]] = data.get("items", [])

        # No nodes in the cluster is definitely not healthy
        if not items:
            self._health_info = "No nodes found"
            return False

        ready_count: int = 0
        total_count: int = len(items)

        for node in items:
            # The conditions list lives in status
            conditions: list[dict[str, Any]] = node.get("status", {}).get("conditions", [])

            for cond in conditions:
                # Ready with status "True" means we can schedule on this node
                if cond.get("type") == "Ready" and cond.get("status") == "True":
                    ready_count += 1
                    break

        all_ready: bool = ready_count == total_count

        # Track how many nodes are ready for info
        self._health_info = f"{ready_count}/{total_count} nodes ready"

        return all_ready
