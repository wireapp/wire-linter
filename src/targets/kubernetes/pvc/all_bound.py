"""Checks if all PersistentVolumeClaims are Bound.

Unbound PVCs mean storage provisioning failed, which silently breaks
services that need persistent storage.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class PvcAllBound(BaseTarget):
    """Checks if all PVCs are Bound.

    Queries every PVC across all namespaces and verifies status.phase == «Bound».
    """

    @property
    def description(self) -> str:
        """Description of what we're checking."""
        return "All PersistentVolumeClaims are Bound"

    @property
    def explanation(self) -> str:
        """Why this check matters."""
        return (
            "Unbound PVCs mean storage provisioning failed. Pods waiting on them "
            "get stuck in Pending. Healthy means every PVC has phase=«Bound»."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check if all PVCs are Bound.

        Returns True if all PVCs have phase=«Bound» (or none exist).
        Raises RuntimeError if kubectl fails.
        """
        cmd_result, data = self.run_kubectl("pvc", all_namespaces=True)

        if data is None:
            raise RuntimeError("Failed to query PVCs from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        if not items:
            self._health_info = "No PVCs found"
            return True

        bound_count: int = 0
        not_bound: list[str] = []

        for pvc in items:
            name: str = pvc.get("metadata", {}).get("name", "unknown")
            namespace: str = pvc.get("metadata", {}).get("namespace", "?")
            phase: str = pvc.get("status", {}).get("phase", "Unknown")

            if phase == "Bound":
                bound_count += 1
            else:
                not_bound.append(f"{namespace}/{name} ({phase})")

        total: int = len(items)
        all_bound: bool = bound_count == total

        if all_bound:
            self._health_info = f"All {total} PVCs are Bound"
        else:
            examples: str = ", ".join(not_bound[:5])
            self._health_info = f"{bound_count}/{total} Bound, not bound: {examples}"

        return all_bound
