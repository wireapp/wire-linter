"""Checks if the legal hold (Secure Hold) service is running.

Legal hold records communications for compliance. It may run as a Kubernetes
deployment or a Docker container outside the cluster.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class LegalholdHealthy(BaseTarget):
    """Check if legalhold pods are running.

    Only runs when expect_legalhold is true.
    """

    # Legalhold is a main-cluster service
    cluster_affinity: str = 'main'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Legal hold service health"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Legal hold records communications of specific users for compliance. "
            "If the legalhold service is not running, recording stops."
        )

    @property
    def unit(self) -> str:
        """No unit — returns boolean."""
        return ""

    def collect(self) -> bool:
        """Check if legalhold pods are running.

        Returns:
            True if at least one legalhold pod is running.

        Raises:
            NotApplicableError: If legal hold is not expected.
        """
        if not self.config.options.expect_legalhold:
            raise NotApplicableError("Legal hold is not enabled in the deployment configuration")

        self.terminal.step("Checking legal hold service health...")

        _result, data = self.run_kubectl("pods")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch pod list")

        items: list[dict[str, Any]] = data.get("items", [])
        legalhold_pods: list[str] = []
        healthy_pods: list[str] = []

        for pod in items:
            name: str = pod.get("metadata", {}).get("name", "")
            phase: str = pod.get("status", {}).get("phase", "")

            # Match pods that look like the legalhold service
            if "legalhold" in name.lower() or "secure-hold" in name.lower():
                legalhold_pods.append(name)
                if phase == "Running":
                    healthy_pods.append(name)

        if not legalhold_pods:
            self._health_info = (
                "No legalhold pods found. The service may run outside Kubernetes "
                "(as a Docker container) or may not be deployed yet."
            )
            return False

        is_healthy: bool = len(healthy_pods) > 0

        if is_healthy:
            self._health_info = f"Legal hold running: {', '.join(healthy_pods)}"
        else:
            self._health_info = f"Legal hold pods found but not running: {', '.join(legalhold_pods)}"

        return is_healthy
