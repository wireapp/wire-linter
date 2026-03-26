"""Fetches Deployment pod template annotations for Wire core services.

When Helm deploys a service, it stamps checksum annotations (like
checksum/config, checksum/secret) into the Deployment's pod template.
These checksums drive rolling restarts when ConfigMaps change: Helm
updates the checksum, which changes the pod template spec, triggering
a rollout.

Extracting these annotations lets the UI compare what the Deployment
expects against what pods are actually running — detecting stale
ConfigMaps where someone updated a ConfigMap but didn't restart the
service.

Produces one data point per service at
« kubernetes/deployments/template_annotations/<service> ».
Value is a JSON string of the annotations dict.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import NotApplicableError
from src.lib.per_service_target import PerServiceTarget, ServiceSpec, WIRE_CORE_SERVICES


class TemplateAnnotations(PerServiceTarget):
    """Fetches pod template annotations from Deployments for each Wire service.

    For each service, queries the Deployment (falling back to StatefulSet)
    and extracts spec.template.metadata.annotations. This is where Helm
    stores checksum/config and checksum/secret annotations that trigger
    rolling restarts when ConfigMaps change.

    Produces a JSON string of the annotations dict. An empty dict means
    the Deployment exists but has no annotations (common for non-Helm
    deployments). None (not_applicable) means the service wasn't found.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Deployment pod template annotations for Wire services"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Helm stamps checksum annotations into Deployment pod templates. "
            "When a ConfigMap changes, Helm updates these checksums, which "
            "triggers a rolling restart. Extracting these lets us compare "
            "what the Deployment expects against what pods are actually running."
        )

    def get_services(self) -> list[ServiceSpec]:
        """Return the 8 core Wire services to check.

        Returns:
            The shared Wire core services list.
        """
        return WIRE_CORE_SERVICES

    def collect_for_service(self, spec: ServiceSpec) -> str | None:
        """Fetch the pod template annotations for a service's Deployment.

        Tries Deployment first (most Wire services use Deployments),
        then falls back to StatefulSet. Extracts the annotations from
        spec.template.metadata.annotations in the workload resource.

        Args:
            spec: Which service to query.

        Returns:
            JSON string of the template annotations dict, or None
            if the service has no Deployment or StatefulSet.
        """
        namespace: str = self.config.cluster.kubernetes_namespace
        service_name: str = spec["name"]

        self.terminal.step(f"Fetching Deployment for '{service_name}'...")

        # Try Deployment first (most Wire services use Deployments)
        _result, parsed = self.run_kubectl(
            f"deployment/{service_name}",
            namespace=namespace,
        )

        # kubectl returns the resource as a dict with a 'kind' field
        if isinstance(parsed, dict) and parsed.get("kind") == "Deployment":
            annotations: dict[str, str] = _extract_template_annotations(parsed)
            self._health_info = _summarize_annotations(annotations)
            return json.dumps(annotations, sort_keys=True)

        # Fallback: some services may be StatefulSets
        self.terminal.step(f"No Deployment found, trying StatefulSet for '{service_name}'...")

        _result, parsed = self.run_kubectl(
            f"statefulset/{service_name}",
            namespace=namespace,
        )

        if isinstance(parsed, dict) and parsed.get("kind") == "StatefulSet":
            annotations = _extract_template_annotations(parsed)
            self._health_info = _summarize_annotations(annotations)
            return json.dumps(annotations, sort_keys=True)

        # Service not deployed as a Deployment or StatefulSet
        raise NotApplicableError("Service not deployed as Deployment or StatefulSet")


def _extract_template_annotations(resource: dict[str, Any]) -> dict[str, str]:
    """Pull annotations from a Deployment/StatefulSet pod template.

    Navigates spec.template.metadata.annotations safely, returning
    an empty dict if any level is missing.

    Args:
        resource: The parsed kubectl JSON for a Deployment or StatefulSet.

    Returns:
        The annotations dict, or empty dict if none present.
    """
    return (
        resource.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("annotations") or {}
    )


def _summarize_annotations(annotations: dict[str, str]) -> str:
    """Build a human-readable summary of the annotations found.

    Args:
        annotations: The template annotations dict.

    Returns:
        Summary string for terminal health_info display.
    """
    # Filter to just checksum-related annotations
    checksum_keys: list[str] = [
        key for key in annotations if key.startswith("checksum/")
    ]

    if not checksum_keys:
        return "No checksum annotations found in pod template"

    # Show the checksum keys and abbreviated values
    parts: list[str] = []
    for key in sorted(checksum_keys):
        value: str = annotations[key]
        # Truncate long hashes for display
        short_value: str = value[:12] + "..." if len(value) > 12 else value
        parts.append(f"{key}={short_value}")

    return f"{len(checksum_keys)} checksum(s): {', '.join(parts)}"
