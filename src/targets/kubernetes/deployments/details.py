"""Fetches detailed Deployment specs and status for Wire core services.

This is the workhorse target for Kubernetes health analysis. It extracts
a curated subset of each Deployment's spec and status, covering:
  - Replica counts and rollout status (stuck rollout detection)
  - Container resource limits and requests
  - Liveness and readiness probe configuration
  - Container images and pull policies
  - Security context settings

Multiple checkers consume this data to evaluate different aspects of
deployment health without each needing its own kubectl call.

Produces one data point per service at
« kubernetes/deployments/details/<service> ».
Value is a JSON string with the curated deployment data.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import NotApplicableError
from src.lib.kubectl import int_or_zero
from src.lib.per_service_target import PerServiceTarget, ServiceSpec, WIRE_CORE_SERVICES


class DeploymentDetails(PerServiceTarget):
    """Fetches comprehensive deployment specs and status for each Wire service.

    For each service, queries the Deployment (falling back to StatefulSet)
    and extracts replica counts, container specs, rollout status, probes,
    resource limits, images, and security context. Returns everything as
    a JSON string so multiple checkers can evaluate different aspects.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Deployment details for Wire services"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Extracts comprehensive deployment specifications for each Wire service "
            "including replica counts, container resource limits, probes, images, "
            "rollout status, and security context. Multiple health checkers consume "
            "this data to evaluate different aspects of deployment health."
        )

    def get_services(self) -> list[ServiceSpec]:
        """Return the 8 core Wire services to check.

        Returns:
            The shared Wire core services list.
        """
        return WIRE_CORE_SERVICES

    def collect_for_service(self, spec: ServiceSpec) -> str | None:
        """Fetch comprehensive deployment details for a service.

        Tries Deployment first, then falls back to StatefulSet.
        Extracts a curated subset of the resource's spec and status.

        Args:
            spec: Which service to query.

        Returns:
            JSON string with deployment details, or None if the service
            has no Deployment or StatefulSet.
        """
        namespace: str = self.config.cluster.kubernetes_namespace
        service_name: str = spec["name"]

        self.terminal.step(f"Fetching deployment details for '{service_name}'...")

        # Try Deployment first (most Wire services use Deployments)
        _result, parsed = self.run_kubectl(
            f"deployment/{service_name}",
            namespace=namespace,
        )

        # kubectl returns the resource as a dict with a 'kind' field
        if isinstance(parsed, dict) and parsed.get("kind") == "Deployment":
            details: dict[str, Any] = _extract_details(parsed)
            self._health_info = _summarize_details(details)
            return json.dumps(details, sort_keys=True)

        # Fallback: some services may be StatefulSets
        self.terminal.step(f"No Deployment found, trying StatefulSet for '{service_name}'...")

        _result, parsed = self.run_kubectl(
            f"statefulset/{service_name}",
            namespace=namespace,
        )

        if isinstance(parsed, dict) and parsed.get("kind") == "StatefulSet":
            details = _extract_details(parsed)
            self._health_info = _summarize_details(details)
            return json.dumps(details, sort_keys=True)

        # Service not found as a Deployment or StatefulSet
        raise NotApplicableError("Service not found as Deployment or StatefulSet")



def _extract_strategy(kind: str, resource_spec: dict[str, Any]) -> str:
    """Read the rollout strategy type from the correct spec field.

    Deployments store this under spec.strategy.type, while StatefulSets
    use spec.updateStrategy.type.

    Args:
        kind: The Kubernetes resource kind ("Deployment" or "StatefulSet").
        resource_spec: The resource's spec dict.

    Returns:
        The strategy type string (e.g. "RollingUpdate"), or empty string
        if not present.
    """
    if kind == "StatefulSet":
        return resource_spec.get("updateStrategy", {}).get("type", "")
    # Deployment (and any other kind) uses "strategy"
    return resource_spec.get("strategy", {}).get("type", "")


def _extract_details(resource: dict[str, Any]) -> dict[str, Any]:
    """Pull a curated subset from a Deployment/StatefulSet.

    Extracts replica counts, rollout status, container specs
    (resources, probes, images, security context).

    Args:
        resource: The parsed kubectl JSON for a Deployment or StatefulSet.

    Returns:
        Dict with curated deployment details.
    """
    resource_spec: dict[str, Any] = resource.get("spec", {})
    resource_status: dict[str, Any] = resource.get("status", {})
    template_spec: dict[str, Any] = (
        resource_spec.get("template", {}).get("spec", {})
    )

    # Extract container details
    containers: list[dict[str, Any]] = []
    for container in template_spec.get("containers", []):
        resources: dict[str, Any] = container.get("resources", {})

        containers.append({
            "name": container.get("name", ""),
            "image": container.get("image", ""),
            "image_pull_policy": container.get("imagePullPolicy", "IfNotPresent"),
            "resources": {
                "requests": resources.get("requests") or {},
                "limits": resources.get("limits") or {},
            },
            "liveness_probe": container.get("livenessProbe"),
            "readiness_probe": container.get("readinessProbe"),
            "security_context": container.get("securityContext"),
        })

    # Extract rollout conditions
    conditions: list[dict[str, str]] = []
    for condition in resource_status.get("conditions", []):
        conditions.append({
            "type": condition.get("type", ""),
            "status": condition.get("status", ""),
            "reason": condition.get("reason", ""),
            "message": condition.get("message", ""),
        })

    return {
        "kind": resource.get("kind", ""),
        "replicas": int_or_zero(resource_spec, "replicas"),
        "ready_replicas": int_or_zero(resource_status, "readyReplicas"),
        "updated_replicas": int_or_zero(resource_status, "updatedReplicas"),
        "available_replicas": int_or_zero(resource_status, "availableReplicas"),
        "unavailable_replicas": int_or_zero(resource_status, "unavailableReplicas"),
        "conditions": conditions,
        "containers": containers,
        # Deployments use "strategy", StatefulSets use "updateStrategy"
        "strategy": _extract_strategy(resource.get("kind", ""), resource_spec),
    }


def _summarize_details(details: dict[str, Any]) -> str:
    """Build a human-readable summary of deployment details.

    Args:
        details: The extracted deployment details dict.

    Returns:
        Summary string for terminal display.
    """
    replicas: int = details.get("replicas", 0)
    ready: int = details.get("ready_replicas", 0)
    containers: list[dict[str, Any]] = details.get("containers", [])

    # Check resource limits
    missing_limits: int = sum(
        1 for c in containers
        if not c.get("resources", {}).get("limits")
    )

    parts: list[str] = [f"{ready}/{replicas} ready"]

    if missing_limits > 0:
        parts.append(f"{missing_limits} container(s) missing limits")

    return ", ".join(parts)
