"""Fetches Pod Disruption Budgets from the Wire namespace.

Without PDBs, a kubectl drain during node maintenance can evict all pods
of a service simultaneously, causing a complete outage. PDBs guarantee a
minimum number of pods stay running during voluntary disruptions.

Produces a single data point at « kubernetes/pods/disruption_budgets ».
Value is a JSON string with PDB details.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class DisruptionBudgets(BaseTarget):
    """Fetches Pod Disruption Budgets from the Wire namespace.

    Queries all PDBs and extracts their configuration and current status.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Pod Disruption Budgets in Wire namespace"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Pod Disruption Budgets (PDBs) prevent all pods of a service from "
            "being evicted simultaneously during node maintenance. Without PDBs, "
            "a kubectl drain can take out an entire service."
        )

    def collect(self) -> str:
        """Fetch all PDBs from the Wire namespace.

        Returns:
            JSON string with PDB count and details.
        """
        namespace: str = self.config.cluster.kubernetes_namespace

        self.terminal.step("Fetching Pod Disruption Budgets...")

        _result, parsed = self.run_kubectl(
            "poddisruptionbudgets", namespace=namespace
        )

        pdbs: list[dict[str, Any]] = []

        if isinstance(parsed, dict):
            for item in parsed.get("items", []):
                pdb_spec: dict[str, Any] = item.get("spec", {})
                pdb_status: dict[str, Any] = item.get("status", {})

                # Extract the selector to know which service this PDB protects
                selector_labels: dict[str, str] = (
                    pdb_spec.get("selector", {}).get("matchLabels", {})
                )

                pdbs.append({
                    "name": item.get("metadata", {}).get("name", ""),
                    "min_available": pdb_spec.get("minAvailable"),
                    "max_unavailable": pdb_spec.get("maxUnavailable"),
                    "selector_labels": selector_labels,
                    "current_healthy": pdb_status.get("currentHealthy", 0) or 0,
                    "desired_healthy": pdb_status.get("desiredHealthy", 0) or 0,
                    "disruptions_allowed": pdb_status.get("disruptionsAllowed", 0) or 0,
                    "expected_pods": pdb_status.get("expectedPods", 0) or 0,
                })

        pdb_count: int = len(pdbs)

        if pdb_count == 0:
            self._health_info = "No PDBs found"
        else:
            zero_allowed: int = sum(
                1 for p in pdbs if p["disruptions_allowed"] == 0
            )
            self._health_info = (
                f"{pdb_count} PDB(s), {zero_allowed} with zero disruptions allowed"
            )

        return json.dumps({
            "pdb_count": pdb_count,
            "pdbs": pdbs,
        }, sort_keys=True)
