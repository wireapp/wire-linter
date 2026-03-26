"""Fetches running pod annotations for Wire core services.

Each pod carries annotations from its Deployment template, including
checksum values that Helm uses to track config versions. Extracting
pod annotations separately from Deployment template annotations lets
the UI detect when pods are running stale configurations — the classic
"someone updated the ConfigMap but didn't restart the service" scenario.

Produces one data point per service at
« kubernetes/pods/annotations/<service> ».
Value is a JSON string mapping pod name to its annotations dict.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import NotApplicableError
from src.lib.per_service_target import PerServiceTarget, ServiceSpec, WIRE_CORE_SERVICES
from src.lib.wire_service_helpers import get_service_pods


class PodAnnotations(PerServiceTarget):
    """Fetches annotations from running pods for each Wire service.

    For each service, finds the running pods (using label selector with
    name-prefix fallback) and extracts their metadata.annotations.
    Combined with the Deployment template annotations target, the UI
    can detect stale ConfigMaps.

    Produces a JSON dict mapping pod name to annotations dict. None
    (not_applicable) means no pods were found for this service.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Running pod annotations for Wire services"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Pod annotations carry the checksum values from the Deployment "
            "template at the time the pod was created. Comparing these against "
            "the current Deployment template annotations reveals whether pods "
            "are running stale configuration."
        )

    def get_services(self) -> list[ServiceSpec]:
        """Return the 8 core Wire services to check.

        Returns:
            The shared Wire core services list.
        """
        return WIRE_CORE_SERVICES

    def collect_for_service(self, spec: ServiceSpec) -> str | None:
        """Fetch annotations from running pods for a service.

        Uses wire_service_helpers.get_service_pods() to find pods by
        label or name prefix. Extracts metadata.annotations from each
        running pod.

        Args:
            spec: Which service to query.

        Returns:
            JSON string of {pod_name: annotations_dict, ...}, or None
            if no pods found for this service.
        """
        namespace: str = self.config.cluster.kubernetes_namespace
        service_name: str = spec["name"]

        self.terminal.step(f"Fetching pods for '{service_name}'...")

        # get_service_pods tries app= label, then name prefix, then
        # all-namespaces as fallback
        _result, pods = get_service_pods(
            service_name, self.run_kubectl, namespace, self.logger
        )

        if not pods:
            raise NotApplicableError("No pods found for service")

        # Build a map of pod name to its annotations
        pod_annotations: dict[str, dict[str, str]] = {}

        for pod in pods:
            pod_name: str = pod.get("metadata", {}).get("name", "unknown")
            annotations: dict[str, str] = (
                pod.get("metadata", {}).get("annotations") or {}
            )
            pod_annotations[pod_name] = annotations

        # Summary for terminal display
        checksum_count: int = _count_pods_with_checksums(pod_annotations)
        self._health_info = (
            f"{len(pod_annotations)} pod(s), "
            f"{checksum_count} with checksum annotations"
        )

        return json.dumps(pod_annotations, sort_keys=True)


def _count_pods_with_checksums(
    pod_annotations: dict[str, dict[str, str]],
) -> int:
    """Count how many pods have at least one checksum/ annotation.

    Args:
        pod_annotations: Map of pod name to annotations dict.

    Returns:
        Number of pods that have checksum-related annotations.
    """
    count: int = 0

    for annotations in pod_annotations.values():
        has_checksum: bool = any(
            key.startswith("checksum/") for key in annotations
        )
        if has_checksum:
            count += 1

    return count
