"""Fetches pod-to-node distribution for Wire core services.

When all pods of a service land on the same node, a single node failure
takes out the entire service. This target maps which node each pod runs
on so the UI can detect poor distribution.

Produces one data point per service at
« kubernetes/pods/distribution/<service> ».
Value is a JSON string with pod-to-node mapping and distribution stats.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import NotApplicableError
from src.lib.per_service_target import PerServiceTarget, ServiceSpec, WIRE_CORE_SERVICES
from src.lib.wire_service_helpers import get_service_pods


class PodDistribution(PerServiceTarget):
    """Maps which node each pod runs on for each Wire service.

    For each service, finds running pods and extracts their node
    assignments. Reports how many unique nodes are used and whether
    all pods are concentrated on a single node.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Pod-to-node distribution for Wire services"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "When all pods of a service land on the same node, a single node "
            "failure takes out the entire service. Spreading pods across nodes "
            "provides real high availability."
        )

    def get_services(self) -> list[ServiceSpec]:
        """Return the 8 core Wire services to check.

        Returns:
            The shared Wire core services list.
        """
        return WIRE_CORE_SERVICES

    def collect_for_service(self, spec: ServiceSpec) -> str | None:
        """Map pod-to-node assignments for a service.

        Args:
            spec: Which service to query.

        Returns:
            JSON string with distribution details, or None if no pods found.
        """
        namespace: str = self.config.cluster.kubernetes_namespace
        service_name: str = spec["name"]

        self.terminal.step(f"Fetching pod distribution for '{service_name}'...")

        _result, pods = get_service_pods(
            service_name, self.run_kubectl, namespace, self.logger
        )

        if not pods:
            raise NotApplicableError("No pods found for service")

        # Map each pod to its node
        node_distribution: dict[str, int] = {}
        pod_nodes: dict[str, str] = {}

        for pod in pods:
            pod_name: str = pod.get("metadata", {}).get("name", "unknown")
            node_name: str = pod.get("spec", {}).get("nodeName", "unscheduled")
            phase: str = pod.get("status", {}).get("phase", "")

            # Only count running pods for distribution analysis
            if phase == "Running":
                pod_nodes[pod_name] = node_name
                node_distribution[node_name] = node_distribution.get(node_name, 0) + 1

        pod_count: int = len(pod_nodes)
        node_count: int = len(node_distribution)
        all_on_single_node: bool = node_count == 1 and pod_count > 1

        if all_on_single_node:
            node_name = next(iter(node_distribution))
            self._health_info = f"All {pod_count} pods on single node: {node_name}"
        else:
            self._health_info = f"{pod_count} pod(s) across {node_count} node(s)"

        return json.dumps({
            "pod_count": pod_count,
            "node_count": node_count,
            "all_on_single_node": all_on_single_node,
            "node_distribution": node_distribution,
            "pod_nodes": pod_nodes,
        }, sort_keys=True)
