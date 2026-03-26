"""Checks if the federator service pods are healthy.

The federator handles federation ingress and egress — it's the gateway for
inter-backend communication. Only deployed when tags.federation: true is set
in the wire-server helm values.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class FederatorHealthy(BaseTarget):
    """Check if federator pods are running and healthy.

    Only runs when expect_federation is true.
    """

    # Federator is a main-cluster service (not calling-cluster)
    cluster_affinity: str = 'main'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federator service health"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The federator is the gateway for federation — it handles incoming "
            "requests from remote backends and outgoing requests to them. If it's "
            "not running, federation is completely broken."
        )

    @property
    def unit(self) -> str:
        """No unit — returns boolean."""
        return ""

    def collect(self) -> bool:
        """Check if federator pods are running.

        Returns:
            True if at least one federator pod is running and ready.

        Raises:
            NotApplicableError: If federation is not expected.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled in the deployment configuration")

        self.terminal.step("Checking federator pod health...")

        _result, data = self.run_kubectl("pods")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch pod list")

        items: list[dict[str, Any]] = data.get("items", [])
        federator_pods: list[str] = []
        healthy_pods: list[str] = []

        for pod in items:
            name: str = pod.get("metadata", {}).get("name", "")
            phase: str = pod.get("status", {}).get("phase", "")

            if "federator" in name.lower() and "migrate" not in name.lower():
                federator_pods.append(name)
                if phase == "Running":
                    # Also check container readiness
                    container_statuses: list[dict[str, Any]] = pod.get("status", {}).get("containerStatuses", [])
                    all_ready: bool = all(cs.get("ready", False) for cs in container_statuses)
                    if all_ready:
                        healthy_pods.append(name)

        if not federator_pods:
            self._health_info = "No federator pods found in the cluster"
            return False

        is_healthy: bool = len(healthy_pods) > 0

        if is_healthy:
            self._health_info = f"Federator healthy: {len(healthy_pods)}/{len(federator_pods)} pods ready"
        else:
            self._health_info = f"Federator unhealthy: 0/{len(federator_pods)} pods ready"

        return is_healthy
