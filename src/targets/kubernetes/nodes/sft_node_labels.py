"""Checks that Kubernetes nodes have SFT scheduling labels.

SFT pods need wire.link/role=sft to land on nodes with the right network
access. Without it, SFT won't start or ends up on the wrong node. See JCT-47.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Labels used by wire-server Helm charts to schedule SFT pods.
# Note: node-role.kubernetes.io/sft is excluded here because Kubernetes role
# labels are key-only by convention value is always empty string, never "sft".
# We check that separately below via key-presence.
_SFT_LABELS: list[str] = [
    "wire.link/role",
    "wire.link/app",
]

# Expected value for wire.link/role or wire.link/app
_SFT_LABEL_VALUE: str = "sft"


class SftNodeLabels(BaseTarget):
    """Checks for SFT scheduling labels on Kubernetes nodes.

    Looks for wire.link/role=sft or wire.link/app=sft on nodes and counts
    how many have the label.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Kubernetes nodes with SFT scheduling labels"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "SFT pods need nodes labeled with wire.link/role=sft so the scheduler "
            "can place them on the right hardware. Without the label, SFT can't "
            "start or ends up in the wrong place (JCT-47)."
        )

    @property
    def unit(self) -> str:
        """Unit shown next to the count."""
        return "nodes"

    def collect(self) -> int:
        """Count nodes with SFT scheduling labels.

        Returns:
            Number of nodes with an SFT scheduling label.

        Raises:
            RuntimeError: If kubectl fails to get node data.
        """
        self.terminal.step("Checking for SFT node labels...")

        _cmd_result, data = self.run_kubectl("nodes")

        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        sft_nodes: list[str] = []
        unlabeled_nodes: list[str] = []

        for item in items:
            node_name: str = item.get("metadata", {}).get("name", "unknown")
            labels: dict[str, str] = item.get("metadata", {}).get("labels", {})

            # Check for wire.link/role or wire.link/app = sft, or the presence of
            # node-role.kubernetes.io/sft (which is key-only, no value check needed).
            has_sft_label: bool = any(
                labels.get(label_key, "").lower() == _SFT_LABEL_VALUE
                for label_key in _SFT_LABELS
            ) or "node-role.kubernetes.io/sft" in labels  # key-only role label

            if has_sft_label:
                sft_nodes.append(node_name)
            else:
                unlabeled_nodes.append(node_name)

        total_nodes: int = len(items)
        sft_count: int = len(sft_nodes)

        if sft_count == 0:
            self._health_info = (
                f"No SFT-labeled nodes found out of {total_nodes} total. "
                "If SFT is deployed, add wire.link/role=sft label to the designated node(s)."
            )
        else:
            self._health_info = (
                f"{sft_count}/{total_nodes} nodes have SFT labels: {', '.join(sft_nodes)}"
            )

        return sft_count
