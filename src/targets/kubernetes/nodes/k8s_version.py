"""Gets the Kubernetes cluster version.

Queries «kubectl get nodes -o json» and extracts the kubeletVersion
from the first node's status.nodeInfo. Works as a reliable cluster
version indicator in healthy clusters.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class K8sVersion(BaseTarget):
    """Gets the Kubernetes cluster version.

    Uses the first node's kubeletVersion as the cluster version.
    In a healthy cluster, all nodes run the same version anyway.
    """

    @property
    def description(self) -> str:
        """What this checks."""
        return "Kubernetes cluster version"

    @property
    def explanation(self) -> str:
        """Why we track this."""
        return (
            "Old Kubernetes versions stop getting security patches and can break Wire upgrades. "
            "We track the version to catch that."
        )

    @property
    def unit(self) -> str:
        """Empty just a version string."""
        return ""

    def collect(self) -> str:
        """Fetch node info and extract the kubelet version string.

        Returns:
            Version string like «v1.28.3» from the first node's nodeInfo.

        Raises:
            RuntimeError: If kubectl fails or no nodes exist.
        """
        # Get the node list as JSON
        cmd_result, data = self.run_kubectl("nodes")

        # If data is None, kubectl bombed or output was unparseable
        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        # items array has one entry per node
        items: list[dict[str, Any]] = data.get("items", [])

        # No nodes means no version to report
        if not items:
            raise RuntimeError("No nodes found in cluster")

        # Pull the version from the first node's kubeletVersion field
        version: str = items[0].get("status", {}).get("nodeInfo", {}).get("kubeletVersion", "unknown")

        # Summarize for the health report
        self._health_info = f"Kubernetes cluster running {version}"

        return version
