"""Counts the number of cert-manager certificate resources in the cluster.

Queries certs across all namespaces using the full CRD name first,
then falls back to the shorthand if that doesn't work.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class CertificateCount(BaseTarget):
    """Counts cert-manager certificate resources.

    Queries all namespaces for certificates.cert-manager.io and gives you
    the total count. Pretty straightforward.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Number of cert-manager certificates"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Tracks how many TLS certificates cert-manager is managing. "
            "If the count drops, someone probably deleted a cert resource by accident."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the collected value."""
        return "certificates"

    def collect(self) -> int:
        """Count all cert-manager certificate resources in the cluster.

        Returns:
            Integer count of certificate resources.

        Raises:
            RuntimeError: If cert-manager isn't installed or we can't query certificates.
        """
        # Try the full CRD name first to avoid hitting other things named « certificates »
        cmd_result, data = self.run_kubectl(
            "certificates.cert-manager.io",
            all_namespaces=True,
        )

        if data is None:
            # Full name didn't work, fall back to the shorthand
            cmd_result2, data = self.run_kubectl(
                "certificates",
                all_namespaces=True,
            )

            if data is None:
                raise RuntimeError("Failed to query certificates (cert-manager may not be installed)")

        items: list[dict[str, Any]] = data.get("items", [])
        count: int = len(items)

        self._health_info = f"{count} certificate resource(s) found"
        return count
