"""Checks CoreDNS pod health in kube-system.

DNS failures cascade to every service in the cluster. If CoreDNS pods
are crashlooping or overloaded, all services experience random failures
but the symptoms look like application bugs, not DNS.

Produces a single data point at « kubernetes/pods/coredns_health ».
Value is a JSON string with CoreDNS pod status summary.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class CoreDnsHealth(BaseTarget):
    """Checks health of CoreDNS pods in kube-system namespace.

    CoreDNS is critical infrastructure — if it's down, nothing works.
    Queries pods with the standard kube-dns label in kube-system.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "CoreDNS pod health"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "CoreDNS handles all cluster DNS resolution. If CoreDNS is down or "
            "degraded, every service fails to resolve internal hostnames. The "
            "symptoms look like random application failures, not DNS."
        )

    def collect(self) -> str:
        """Fetch CoreDNS pod status from kube-system.

        Returns:
            JSON string with CoreDNS pod health summary.
        """
        self.terminal.step("Checking CoreDNS pods in kube-system...")

        # CoreDNS pods use the k8s-app=kube-dns label
        _result, parsed = self.run_kubectl(
            "pods",
            namespace="kube-system",
            selector="k8s-app=kube-dns",
        )

        pods: list[dict[str, Any]] = []
        running_count: int = 0
        ready_count: int = 0

        if isinstance(parsed, dict):
            for pod in parsed.get("items", []):
                pod_name: str = pod.get("metadata", {}).get("name", "unknown")
                phase: str = pod.get("status", {}).get("phase", "")

                # Check container readiness
                container_statuses: list[dict[str, Any]] = (
                    pod.get("status", {}).get("containerStatuses", [])
                )
                all_ready: bool = all(
                    cs.get("ready", False) for cs in container_statuses
                ) if container_statuses else False

                # Sum up restart counts
                total_restarts: int = sum(
                    cs.get("restartCount", 0) for cs in container_statuses
                )

                is_running: bool = phase == "Running"
                if is_running:
                    running_count += 1
                if is_running and all_ready:
                    ready_count += 1

                pods.append({
                    "name": pod_name,
                    "phase": phase,
                    "ready": all_ready,
                    "restarts": total_restarts,
                })

        total_pods: int = len(pods)

        if total_pods == 0:
            self._health_info = "No CoreDNS pods found"
        elif ready_count == total_pods:
            self._health_info = f"All {total_pods} CoreDNS pod(s) healthy"
        else:
            self._health_info = (
                f"{ready_count}/{total_pods} CoreDNS pod(s) ready"
            )

        return json.dumps({
            "total_pods": total_pods,
            "running_pods": running_count,
            "ready_pods": ready_count,
            "pods": pods,
        }, sort_keys=True)
