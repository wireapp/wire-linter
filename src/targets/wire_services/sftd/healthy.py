"""SFTd (conference calling) health check target.

Checks whether all SFTd pods are running with all containers ready.
Uses kubectl to query pod status and evaluates overall service health.
SFTd is the Selective Forwarding Thingy (media server) that enables
group audio/video calls; its unavailability disables conference calling.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.wire_service_helpers import count_replicas, get_service_pods, is_service_healthy, replica_label


class SftdHealthy(BaseTarget):
    """Checks if SFTd (conference calling) service is healthy.

    Queries Kubernetes for all SFTd pods and verifies they are all
    in Running state with all containers ready.
    """

    @property
    def description(self) -> str:
        """What we check."""
        return "SFTd (conference calling) - all replicas running"

    @property
    def explanation(self) -> str:
        """SFTd is the media server for group calls. If pods aren't healthy, users can't join or stay in conference calls."""
        return (
            "SFTd is the media server for group audio/video calls. Unhealthy pods "
            "prevent users from joining or maintaining conference calls."
        )

    def collect(self) -> bool:
        """Check if all SFTd pods are running and ready."""
        self.terminal.step("Checking SFTd pod status...")

        cmd_result, pods = get_service_pods("sftd", self.run_kubectl, self.config.cluster.kubernetes_namespace, self.logger)
        healthy: bool = is_service_healthy(pods)
        running: int = count_replicas(pods)

        if healthy:
            self._dynamic_description = f"SFTd (conference calling) - {replica_label(running)}"

        self._health_info = f"{running} running pods, {'all healthy' if healthy else 'not all ready'}"

        return healthy
