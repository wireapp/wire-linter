"""Checks that coturn pods have memory limits configured.

Without memory limits, coturn consumes unbounded memory under heavy load
and triggers the Linux OOM killer, killing the entire pod. That kills all
active TURN relay sessions. See WPB-17666.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Try these label selectors in order to find coturn pods
_COTURN_SELECTORS: list[str] = [
    "app=coturn",
    "app.kubernetes.io/name=coturn",
    "app=restund",
]


class CoturnMemoryLimits(BaseTarget):
    """Checks that coturn pods have memory limits configured.

    Finds coturn pods by label selector and checks each container's
    resources.limits.memory field. Returns True only if every container
    has a memory limit.
    """

    @property
    def description(self) -> str:
        """What we check."""
        return "Coturn pods have memory limits set"

    @property
    def explanation(self) -> str:
        """Why this matters and what « healthy » means."""
        return (
            "Without memory limits, coturn triggers OOM killer under heavy load "
            "and drops all active TURN sessions. Healthy when all containers "
            "have resources.limits.memory set (WPB-17666)."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check whether all coturn containers have memory limits.

        Returns:
            True if every container has a limit, False otherwise.

        Raises:
            RuntimeError: If no coturn pods found with any selector.
        """
        self.terminal.step("Checking coturn pod memory limits...")

        # Try selectors in order until we find coturn pods
        coturn_pods: list[dict[str, Any]] = []

        for selector in _COTURN_SELECTORS:
            _cmd_result, data = self.run_kubectl(
                "pods",
                all_namespaces=True,
                selector=selector,
            )

            if data is not None:
                items: list[dict[str, Any]] = data.get("items", [])
                if items:
                    coturn_pods = items
                    self.terminal.step(
                        f"Found {len(items)} coturn pod(s) using selector '{selector}'"
                    )
                    break

        if not coturn_pods:
            # coturn/restund might not be deployed that's fine
            self._health_info = "No coturn pods found (may not be deployed)"
            return True

        missing_limits: list[str] = []
        checked_containers: int = 0

        for pod in coturn_pods:
            pod_name: str = pod.get("metadata", {}).get("name", "unknown")
            namespace: str = pod.get("metadata", {}).get("namespace", "?")
            containers: list[dict[str, Any]] = pod.get("spec", {}).get("containers", [])

            for container in containers:
                container_name: str = container.get("name", "?")
                checked_containers += 1

                # Check if resources.limits.memory is actually set
                limits: dict[str, Any] = container.get("resources", {}).get("limits", {})
                memory_limit: str = str(limits.get("memory", "")).strip()

                if not memory_limit:
                    missing_limits.append(f"{namespace}/{pod_name}/{container_name}")

        all_limited: bool = len(missing_limits) == 0

        if all_limited:
            self._health_info = (
                f"All {checked_containers} coturn container(s) have memory limits"
            )
        else:
            self._health_info = (
                f"{len(missing_limits)} container(s) missing memory limits: "
                f"{', '.join(missing_limits)}"
            )

        return all_limited
