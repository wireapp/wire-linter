"""Checks for ephemeral/test databases in production.

databases-ephemeral and fake-aws are test charts with zero persistence.
Pod restart = total data loss.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class EphemeralInProduction(BaseTarget):
    """Checks for ephemeral/test deployments in production.

    Looks for databases-ephemeral and fake-aws Helm releases or deployments.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "No ephemeral/test databases in production"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Test charts = zero persistence, pod restart = data loss. "
            "Healthy when none are deployed."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> str:
        """Check for ephemeral/test deployments.

        Returns:
            «production» if none found, «ephemeral» if any detected.
        """
        self.terminal.step("Checking for ephemeral/test deployments...")

        cmd_result, data = self.run_kubectl("deployments", all_namespaces=True)

        ephemeral_found: list[str] = []

        if isinstance(data, dict):
            for item in data.get("items", []):
                name: str = item.get("metadata", {}).get("name", "")
                namespace: str = item.get("metadata", {}).get("namespace", "?")

                if "ephemeral" in name.lower() or "fake-aws" in name.lower():
                    ephemeral_found.append(f"{namespace}/{name}")

        # Check statefulsets too
        cmd_result2, ss_data = self.run_kubectl("statefulsets", all_namespaces=True)

        if isinstance(ss_data, dict):
            for item in ss_data.get("items", []):
                name = item.get("metadata", {}).get("name", "")
                namespace = item.get("metadata", {}).get("namespace", "?")

                if "ephemeral" in name.lower() or "fake-aws" in name.lower():
                    ephemeral_found.append(f"{namespace}/{name}")

        if ephemeral_found:
            self._health_info = (
                f"WARNING: Ephemeral/test deployments found: "
                f"{', '.join(ephemeral_found)}"
            )
            return "ephemeral"

        self._health_info = "No ephemeral/test deployments detected"
        return "production"
