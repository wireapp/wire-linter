"""Checks if all TLS certificates are in Ready state.

Tries the full CRD name « certificates.cert-manager.io » first since it's
less ambiguous, then falls back to just « certificates » if that doesn't work.
Checks the Ready condition on each certificate.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class CertificatesAllReady(BaseTarget):
    """Checks if all TLS certificates are in Ready state.

    Uses the fully-qualified cert-manager CRD name first to avoid collisions,
    falls back to the short name if needed. Everything has to be Ready=True
    or the whole thing fails.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "All TLS certificates are in Ready state"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "If certs aren't ready, cert-manager failed to issue or renew them. "
            "Clients hit TLS errors. Healthy means every certificate has Ready=True."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement. Empty because this is just True or False."""
        return ""

    def collect(self) -> bool:
        """Query cert-manager certificates and verify all are Ready.

        Returns:
            True if all certificates are ready (or there are none), False if any is not ready.

        Raises:
            RuntimeError: If cert-manager isn't installed or we can't query certificates.
        """
        # Try the full CRD name first to avoid collisions with other things named « certificates »
        cmd_result, data = self.run_kubectl(
            "certificates.cert-manager.io",
            all_namespaces=True,
        )

        if data is None:
            # Full name didn't work, try the shorthand
            cmd_result2, data = self.run_kubectl(
                "certificates",
                all_namespaces=True,
            )

            # Both failed. cert-manager's not installed.
            if data is None:
                raise RuntimeError("Failed to query certificates (cert-manager may not be installed)")

        # Pull out the list of certificates from the JSON
        items: list[dict[str, Any]] = data.get("items", [])

        # No certificates at all is technically fine. Nothing to be not-ready.
        if not items:
            self._health_info = "No certificates found"
            return True

        ready_count: int = 0
        total_count: int = len(items)

        for cert in items:
            # Conditions live in status.conditions
            conditions: list[dict[str, Any]] = cert.get("status", {}).get("conditions", [])

            for cond in conditions:
                # Ready=True means the cert is valid and current
                if cond.get("type") == "Ready" and cond.get("status") == "True":
                    ready_count += 1
                    break

        all_ready: bool = ready_count == total_count

        # Track what we found
        self._health_info = f"{ready_count}/{total_count} certificates ready"

        return all_ready
