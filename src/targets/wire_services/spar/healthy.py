"""Spar (SSO/SCIM) health check.

Queries k8s to check if all Spar pods are running and healthy. If Spar
goes down, enterprise users can't authenticate and automated user
provisioning stops working."""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class SparHealthy(BaseTarget):
    """Checks if Spar (SSO/SCIM) service is healthy."""

    @property
    def description(self) -> str:
        return "Spar (SSO/SCIM) - all replicas running"

    @property
    def explanation(self) -> str:
        return (
            "Spar handles SAML SSO and SCIM provisioning. If pods aren't ready, "
            "enterprise users can't authenticate and automated provisioning stops working."
        )

    def collect(self) -> bool:
        """Check if all Spar pods are running and healthy."""
        self.terminal.step("Checking Spar pod status...")

        cmd_result, pods = get_service_pods("spar", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)
        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Spar (SSO/SCIM) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
