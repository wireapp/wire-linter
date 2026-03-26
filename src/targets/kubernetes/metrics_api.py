"""Checks if the Kubernetes Metrics API is available.

Runs `kubectl top nodes --no-headers` to test whether the metrics-server
is installed and responding. Returns True if the command succeeds.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class MetricsApi(BaseTarget):
    """Checks if the Kubernetes Metrics API is available.

    Uses `kubectl top nodes` as a lightweight probe if metrics-server
    is absent or unhealthy the command returns a non-zero exit code.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Kubernetes Metrics API is available (kubectl top)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Without the Metrics API, HPA autoscaling and kubectl top do not work. "
            "Healthy when metrics-server responds to kubectl top nodes."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Run kubectl top nodes and report whether it succeeded.

        Returns:
            True if metrics-server responded successfully, False otherwise.
        """
        # kubectl top nodes fails if metrics-server is not installed or not ready
        result = self.run_kubectl_raw(["top", "nodes", "--no-headers"])

        available: bool = result.success

        # Optional: secondary health assessment (informational only)
        self._health_info = "Metrics API available" if available else "Metrics API not available"

        return available
