"""Fetches endpoint counts for Wire core services.

A Kubernetes Service with zero endpoints means traffic goes to a black
hole. This happens when label selectors don't match any pods, all pods
are unhealthy, or the service is misconfigured.

Produces one data point per service at
« kubernetes/endpoints/service_endpoints/<service> ».
Value is the number of ready endpoint addresses (int).
"""

from __future__ import annotations

from typing import Any

# Ours
from src.lib.base_target import NotApplicableError
from src.lib.per_service_target import PerServiceTarget, ServiceSpec, WIRE_CORE_SERVICES


class ServiceEndpoints(PerServiceTarget):
    """Fetches the count of ready endpoints for each Wire service.

    For each service, queries the matching Endpoints resource and counts
    the number of ready addresses. A count of 0 means the service is
    effectively unreachable.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Service endpoint counts for Wire services"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "A Kubernetes Service with zero endpoints means traffic goes nowhere. "
            "This happens when label selectors don't match pods, all pods are "
            "unhealthy, or the service is misconfigured."
        )

    @property
    def unit(self) -> str:
        """Display unit for the metric."""
        return "endpoints"

    def get_services(self) -> list[ServiceSpec]:
        """Return the 8 core Wire services to check.

        Returns:
            The shared Wire core services list.
        """
        return WIRE_CORE_SERVICES

    def collect_for_service(self, spec: ServiceSpec) -> int | None:
        """Count ready endpoints for a service.

        Fetches the Endpoints resource matching the service name and
        counts all addresses across all subsets.

        Args:
            spec: Which service to query.

        Returns:
            Number of ready endpoint addresses, or None if no Endpoints
            resource exists for this service.
        """
        namespace: str = self.config.cluster.kubernetes_namespace
        service_name: str = spec["name"]

        self.terminal.step(f"Fetching endpoints for '{service_name}'...")

        _result, parsed = self.run_kubectl(
            f"endpoints/{service_name}",
            namespace=namespace,
        )

        if not isinstance(parsed, dict) or parsed.get("kind") != "Endpoints":
            raise NotApplicableError("No Endpoints resource found for service")

        # Count ready addresses across all subsets
        ready_count: int = 0
        subsets: list[dict[str, Any]] = parsed.get("subsets", [])

        for subset in subsets:
            addresses: list[dict[str, Any]] = subset.get("addresses", [])
            ready_count += len(addresses)

        # Also note not-ready endpoints for health_info
        not_ready_count: int = 0
        for subset in subsets:
            not_ready: list[dict[str, Any]] = subset.get("notReadyAddresses", [])
            not_ready_count += len(not_ready)

        if not_ready_count > 0:
            self._health_info = (
                f"{ready_count} ready, {not_ready_count} not ready"
            )
        else:
            self._health_info = f"{ready_count} ready endpoint(s)"

        return ready_count
