"""Checks federator replica count.

Reports desired vs ready replicas for the federator deployment.
Only runs when federation is expected.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class FederatorReplicas(BaseTarget):
    """Check federator replica count (desired vs ready).

    Only runs when expect_federation is true.
    """

    # Federator is a main-cluster service
    cluster_affinity: str = 'main'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federator replica count"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The federator handles all federation traffic. Having insufficient "
            "replicas means federation may be slow or unreliable."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check federator deployment replica count.

        Returns:
            JSON string with replica details.

        Raises:
            NotApplicableError: If federation is not expected.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")

        self.terminal.step("Checking federator replica count...")

        try:
            _result, deploy_data = self.run_kubectl("deployment/federator", output_format="json")
        except RuntimeError:
            raise RuntimeError("Cannot fetch federator deployment")

        if not isinstance(deploy_data, dict):
            raise RuntimeError("Cannot parse federator deployment")

        spec: dict[str, Any] = deploy_data.get("spec", {})
        status: dict[str, Any] = deploy_data.get("status", {})

        desired: int = spec.get("replicas", 0)
        ready: int = status.get("readyReplicas", 0)
        available: int = status.get("availableReplicas", 0)

        result: dict[str, Any] = {
            "desired": desired,
            "ready": ready,
            "available": available,
        }

        if ready >= desired and desired > 0:
            self._health_info = f"Federator: {ready}/{desired} replicas ready"
        elif desired == 0:
            self._health_info = "Federator: 0 replicas desired (scaled to zero?)"
        else:
            self._health_info = f"Federator: only {ready}/{desired} replicas ready"

        return json.dumps(result)
