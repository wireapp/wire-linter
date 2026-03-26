"""Checks for pods with high restart counts across the cluster.

High restart counts indicate crashlooping or OOM-killed containers.
Catches problems that « pods running » alone misses a pod can be
running but have restarted hundreds of times.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget

# Restart count above this threshold is considered noteworthy
_RESTART_THRESHOLD: int = 5


class RestartCounts(BaseTarget):
    """Counts pods with high restart counts.

    Queries all pods across all namespaces and identifies those with
    restart counts above the threshold. Returns the count of pods with
    high restarts.
    """

    @property
    def description(self) -> str:
        """Short description of what we're checking."""
        return "Pods with high restart counts"

    @property
    def explanation(self) -> str:
        """Why we care about restart counts."""
        return (
            "High restart counts indicate crashlooping or OOM-killed containers. "
            "A pod can look healthy but actually be restarting constantly. "
            "We flag anything over 5 restarts."
        )

    @property
    def unit(self) -> str:
        """Display unit for the metric."""
        return "pods"

    def collect(self) -> int:
        """Count pods with too many restarts.

        Returns:
            Number of pods with restarts > threshold.

        Raises:
            RuntimeError: If kubectl fails to return pod data.
        """
        cmd_result, data = self.run_kubectl("pods", all_namespaces=True)

        if data is None:
            raise RuntimeError("Failed to get pods from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        # Collect pods with high restart counts
        high_restart_pods: list[str] = []

        for pod in items:
            pod_name: str = pod.get("metadata", {}).get("name", "unknown")
            namespace: str = pod.get("metadata", {}).get("namespace", "?")
            container_statuses: list[dict[str, Any]] = (
                pod.get("status", {}).get("containerStatuses", [])
            )

            # Add up restarts across all containers
            total_restarts: int = sum(
                cs.get("restartCount", 0) for cs in container_statuses
            )

            if total_restarts > _RESTART_THRESHOLD:
                high_restart_pods.append(f"{namespace}/{pod_name} ({total_restarts})")

        count: int = len(high_restart_pods)

        if count == 0:
            self._health_info = f"No pods with >{_RESTART_THRESHOLD} restarts"
        else:
            # Show first 5 examples
            examples: str = ", ".join(high_restart_pods[:5])
            suffix: str = f" (+{count - 5} more)" if count > 5 else ""
            self._health_info = f"{count} pods with high restarts: {examples}{suffix}"

        return count
