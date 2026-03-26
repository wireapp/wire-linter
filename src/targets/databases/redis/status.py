"""Checks if the Redis ephemeral master pod is running in Kubernetes.

Uses kubectl to query for Redis pods by label selector. Tries the
preferred label 'app.kubernetes.io/name=redis-ephemeral' first, then
falls back to 'app=redis'. This is the only database target that uses
kubectl instead of SSH, because Redis runs as a Kubernetes pod.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class RedisStatus(BaseTarget):
    """Checks Redis pod running status.

    Queries the Kubernetes API for Redis pods and inspects their phase
    to determine whether the ephemeral master is running.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Redis ephemeral master is running"

    @property
    def explanation(self) -> str:
        """Why it matters."""
        return (
            "Redis stores sessions and ephemeral state. Without the master pod "
            "running, Wire services lose their cache and session store."
        )

    def collect(self) -> str:
        """Returns «running» if a Redis pod is active, «not running» if not.

        Raises:
            RuntimeError: No Redis pods found under any label selector.
        """
        self.terminal.step("Checking Redis status via kubectl...")

        selectors = [
            "app.kubernetes.io/name=redis-ephemeral",  # Helm standard
            "app=redis",                                # legacy fallback
        ]

        items: list[dict[str, Any]] = []
        got_valid_response: bool = False

        for selector in selectors:
            cmd_result, data = self.run_kubectl("pods", selector=selector)

            if data is None:
                continue

            got_valid_response = True
            items = data.get("items", [])

            if items:
                break

        if not got_valid_response:
            raise RuntimeError("Could not find Redis pods")

        for pod in items:
            phase: str = pod.get("status", {}).get("phase", "")

            if phase == "Running":
                self._health_info = "Redis pod is running"
                return "running"

        self._health_info = f"{len(items)} pods found, none running"
        return "not running"
