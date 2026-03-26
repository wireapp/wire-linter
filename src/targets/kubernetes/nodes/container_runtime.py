"""Get the container runtime from Kubernetes nodes.

Pull the containerRuntimeVersion field from kubectl get nodes and tell
you what runtime(s) are actually in use.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class ContainerRuntime(BaseTarget):
    """Get the container runtime from each node.

    Grab containerRuntimeVersion from status.nodeInfo on each node and report
    back the unique runtimes.
    """

    @property
    def description(self) -> str:
        """What this checks."""
        return "Kubernetes container runtime"

    @property
    def explanation(self) -> str:
        """Why we're tracking this."""
        return (
            "So you know what runtime you're using (containerd, CRI-O, etc). If "
            "runtimes are mixed across nodes, you get weird behavior and it's a pain to debug."
        )

    def collect(self) -> str:
        """Get the container runtimes in use.

        Returns:
            Comma-separated list of unique runtimes (e.g., « containerd://1.7.2 »).

        Raises:
            RuntimeError: If kubectl fails or there are no nodes.
        """
        cmd_result, data = self.run_kubectl("nodes")

        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        if not items:
            raise RuntimeError("No nodes found in cluster")

        # Grab unique runtimes from all nodes
        runtimes: set[str] = set()
        for item in items:
            runtime: str = (
                item.get("status", {})
                .get("nodeInfo", {})
                .get("containerRuntimeVersion", "unknown")
            )
            runtimes.add(runtime)

        # Sort it so output is consistent
        runtime_list: list[str] = sorted(runtimes)

        if len(runtime_list) == 1:
            self._health_info = f"All {len(items)} nodes use {runtime_list[0]}"
        else:
            self._health_info = f"Mixed runtimes across {len(items)} nodes: {', '.join(runtime_list)}"

        return ", ".join(runtime_list)
