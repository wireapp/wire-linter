"""Checks if the Prometheus/Grafana monitoring stack is running.

If monitoring goes down, you find out about problems when users start calling.
This looks for monitoring pods in the monitoring namespace.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class MonitoringStack(BaseTarget):
    """Checks if the monitoring stack is running.

    Looks for prometheus/grafana pods in the monitoring namespace, or searches
    all namespaces if nothing's there. Just needs to see prometheus and/or
    grafana actually running.
    """

    @property
    def description(self) -> str:
        """What we're checking for."""
        return "Prometheus/Grafana monitoring stack running"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "If monitoring's down, nobody knows there's a problem until users call. "
            "Good as long as prometheus and/or grafana are running."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement it's just a yes/no check."""
        return ""

    def collect(self) -> bool:
        """Check if monitoring pods are running.

        Returns True if we find any prometheus/grafana pods running, False otherwise.
        """
        self.terminal.step("Checking monitoring stack...")

        # Start with the monitoring namespace
        cmd_result, data = self.run_kubectl("pods", namespace="monitoring")

        monitoring_pods: list[str] = []

        if isinstance(data, dict) and data.get("items"):
            for pod in data["items"]:
                name: str = pod.get("metadata", {}).get("name", "")
                phase: str = pod.get("status", {}).get("phase", "")
                # Only count actual monitoring stuff skip random other pods that
                # happen to live in the namespace
                if phase == "Running" and (
                    "prometheus" in name.lower()
                    or "grafana" in name.lower()
                    or "alertmanager" in name.lower()
                ):
                    monitoring_pods.append(name)

        # Nothing found yet? Search everywhere
        if not monitoring_pods:
            cmd_result2, all_data = self.run_kubectl("pods", all_namespaces=True)

            if isinstance(all_data, dict):
                for pod in all_data.get("items", []):
                    name = pod.get("metadata", {}).get("name", "")
                    phase = pod.get("status", {}).get("phase", "")
                    # Grab any prometheus/grafana pods we find
                    if phase == "Running" and (
                        "prometheus" in name.lower()
                        or "grafana" in name.lower()
                        or "alertmanager" in name.lower()
                    ):
                        monitoring_pods.append(name)

        has_monitoring: bool = len(monitoring_pods) > 0

        if has_monitoring:
            # Break down what we found
            has_prometheus: bool = any("prometheus" in p.lower() for p in monitoring_pods)
            has_grafana: bool = any("grafana" in p.lower() for p in monitoring_pods)
            has_alertmanager: bool = any("alertmanager" in p.lower() for p in monitoring_pods)

            parts: list[str] = []
            if has_prometheus:
                parts.append("Prometheus")
            if has_grafana:
                parts.append("Grafana")
            if has_alertmanager:
                parts.append("Alertmanager")

            self._health_info = (
                f"{', '.join(parts)} running ({len(monitoring_pods)} pods)"
            )
        else:
            self._health_info = "No monitoring pods found"

        return has_monitoring
