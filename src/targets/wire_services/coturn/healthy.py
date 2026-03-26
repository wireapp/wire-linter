"""Coturn (TURN server) health check target.

Checks whether all Coturn pods are running with all containers ready.
Uses kubectl to query pod status. Coturn provides TURN relay services
for WebRTC audio/video calls, so when it's unhealthy, call quality
degrades for users behind strict NAT.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class CoturnHealthy(BaseTarget):
    """Checks if Coturn (TURN server) service is healthy.

    Queries Kubernetes for all Coturn pods and verifies they're all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Coturn (TURN server) - all replicas running"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Coturn provides TURN relay for WebRTC calls. Unhealthy pods degrade "
            "audio/video call quality for users behind restrictive NAT or firewalls."
        )

    def collect(self) -> bool:
        """Check if all Coturn pods are running and healthy.

        Returns:
            True if at least one pod exists and all are Running + Ready.
        """
        self.terminal.step("Checking Coturn pod status...")

        cmd_result, pods = get_service_pods("coturn", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)

        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"Coturn (TURN server) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
