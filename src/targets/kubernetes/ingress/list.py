"""Lists all Kubernetes Ingress resources across all namespaces.

Captures the ingress configuration so the linter can verify routing
rules, TLS settings, and detect misconfigured or missing ingresses.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class IngressList(BaseTarget):
    """Lists all Kubernetes Ingress resources.

    Queries ingresses across all namespaces and returns a
    comma-separated list of ingress names with their hosts.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Kubernetes Ingress resources"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Ingress resources define how external traffic reaches Wire services. "
            "Missing or misconfigured ingresses cause connection failures for users."
        )

    def collect(self) -> str:
        """Fetch all ingress resources and return a summary.

        Returns:
            Comma-separated list of ingress names and their hosts.

        Raises:
            RuntimeError: If kubectl fails to return ingress data.
        """
        cmd_result, data = self.run_kubectl("ingress", all_namespaces=True)

        if data is None:
            raise RuntimeError("Failed to query ingress resources from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        if not items:
            self._health_info = "No ingress resources found"
            return ""

        # Build a summary line for each ingress: "name (host1, host2)"
        entries: list[str] = []
        for item in items:
            name: str = item.get("metadata", {}).get("name", "unknown")
            namespace: str = item.get("metadata", {}).get("namespace", "?")

            # Extract hostnames from the ingress rules
            rules: list[dict[str, Any]] = item.get("spec", {}).get("rules", [])
            hosts: list[str] = [r.get("host", "?") for r in rules if r.get("host")]

            host_str: str = ", ".join(hosts) if hosts else "no host"
            entries.append(f"{namespace}/{name} ({host_str})")

        self._health_info = f"{len(items)} ingress resource(s)"
        return ", ".join(entries)
