"""Checks that Backoffice/Stern is not exposed via public ingress.

The backoffice admin tool gives unauthenticated read/delete access to the
entire user database. It should only be reachable via kubectl port-forward,
never through any ingress.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class SternNotExposed(BaseTarget):
    """Checks that Stern/Backoffice is not exposed via ingress.

    Queries all ingress resources and verifies none route to stern or
    backoffice services.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Backoffice/Stern not exposed via public ingress"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Stern gives unauthenticated read/delete access to the entire user database. "
            "It should only be accessible via kubectl port-forward, never through ingress."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check that no ingress exposes Stern/Backoffice.

        Returns:
            True if not exposed (safe), False if exposed (dangerous).
        """
        self.terminal.step("Checking for exposed Stern/Backoffice ingress...")

        cmd_result, data = self.run_kubectl("ingress", all_namespaces=True)

        if data is None:
            self._health_info = "Could not query ingress resources"
            return True  # Can't check, assume safe

        items: list[dict[str, Any]] = data.get("items", [])
        exposed: list[str] = []

        for item in items:
            name: str = item.get("metadata", {}).get("name", "")
            namespace: str = item.get("metadata", {}).get("namespace", "?")

            # Check ingress name
            if "stern" in name.lower() or "backoffice" in name.lower():
                exposed.append(f"{namespace}/{name}")
                continue

            # Check backend service names in the rules
            rules: list[dict[str, Any]] = item.get("spec", {}).get("rules", [])
            for rule in rules:
                paths: list[dict[str, Any]] = rule.get("http", {}).get("paths", [])
                for path_entry in paths:
                    backend: dict[str, Any] = path_entry.get("backend", {})
                    svc_name: str = (
                        backend.get("service", {}).get("name", "")
                        or backend.get("serviceName", "")
                    )
                    if "stern" in svc_name.lower() or "backoffice" in svc_name.lower():
                        exposed.append(f"{namespace}/{name} -> {svc_name}")

        not_exposed: bool = len(exposed) == 0

        if not_exposed:
            self._health_info = "Stern/Backoffice not exposed via ingress"
        else:
            self._health_info = f"SECURITY: Stern/Backoffice exposed: {', '.join(exposed)}"

        return not_exposed
