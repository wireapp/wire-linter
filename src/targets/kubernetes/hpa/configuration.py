"""Fetches Horizontal Pod Autoscaler configuration from the Wire namespace.

HPAs auto-scale services based on metrics. Misconfigured HPAs can cause
problems: minReplicas=1 defeats HA, maxReplicas too low prevents scaling
under load, or current == max means the service is pegged at its ceiling.

Produces a single data point at « kubernetes/hpa/configuration ».
Value is a JSON string with HPA details.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class HpaConfiguration(BaseTarget):
    """Fetches HPA configuration and status from the Wire namespace.

    Queries all HPAs and extracts their target references, replica
    bounds, and current scaling state.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Horizontal Pod Autoscaler configuration"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "HPAs auto-scale services based on CPU/memory metrics. Misconfigured "
            "HPAs can leave services under-provisioned (maxReplicas too low) or "
            "without HA (minReplicas=1). If current replicas equal max, the "
            "service may be struggling to keep up with load."
        )

    def collect(self) -> str:
        """Fetch all HPAs from the Wire namespace.

        Returns:
            JSON string with HPA count and details.
        """
        namespace: str = self.config.cluster.kubernetes_namespace

        self.terminal.step("Fetching Horizontal Pod Autoscalers...")

        _result, parsed = self.run_kubectl(
            "horizontalpodautoscalers", namespace=namespace
        )

        hpas: list[dict[str, Any]] = []

        if isinstance(parsed, dict):
            for item in parsed.get("items", []):
                hpa_spec: dict[str, Any] = item.get("spec", {})
                hpa_status: dict[str, Any] = item.get("status", {})

                # Extract the scale target (which deployment this HPA controls)
                scale_target: dict[str, str] = hpa_spec.get("scaleTargetRef", {})

                # Extract metrics configuration
                metrics: list[dict[str, Any]] = []
                for metric in hpa_spec.get("metrics", []):
                    metric_type: str = metric.get("type", "")
                    metric_info: dict[str, Any] = {"type": metric_type}

                    if metric_type == "Resource":
                        resource: dict[str, Any] = metric.get("resource", {})
                        metric_info["name"] = resource.get("name", "")
                        target: dict[str, Any] = resource.get("target", {})
                        metric_info["target_type"] = target.get("type", "")
                        metric_info["target_value"] = (
                            target.get("averageUtilization")
                            or target.get("averageValue")
                            or target.get("value")
                        )

                    metrics.append(metric_info)

                hpas.append({
                    "name": item.get("metadata", {}).get("name", ""),
                    "target_kind": scale_target.get("kind", ""),
                    "target_name": scale_target.get("name", ""),
                    "min_replicas": hpa_spec.get("minReplicas", 1),
                    "max_replicas": hpa_spec.get("maxReplicas", 0),
                    "current_replicas": hpa_status.get("currentReplicas", 0) or 0,
                    "desired_replicas": hpa_status.get("desiredReplicas", 0) or 0,
                    "metrics": metrics,
                })

        hpa_count: int = len(hpas)

        if hpa_count == 0:
            self._health_info = "No HPAs configured"
        else:
            pegged: int = sum(
                1 for h in hpas
                if h["current_replicas"] >= h["max_replicas"] and h["max_replicas"] > 0
            )
            parts: list[str] = [f"{hpa_count} HPA(s)"]
            if pegged > 0:
                parts.append(f"{pegged} at max capacity")
            self._health_info = ", ".join(parts)

        return json.dumps({
            "hpa_count": hpa_count,
            "hpas": hpas,
        }, sort_keys=True)
