"""Checks brig's federation domain vs cluster domain.

If they don't match, federation API calls fail and cross-team mentions break
(even with valid TLS). WPB-17553.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class BrigFederationDomain(BaseTarget):
    """Checks brig's federation domain against cluster domain.

    Fetches brig's ConfigMap and compares optSettings.setFederationDomain
    with the cluster domain. Mismatch = wrong domain advertised, federation breaks.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Brig federation domain matches cluster domain"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "If brig's setFederationDomain doesn't match the cluster domain, "
            "federation API calls fail and cross-team mentions break."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Compare brig's federation domain with cluster domain.

        Returns:
            True if they match, False if different or not set.

        Raises:
            RuntimeError: If brig ConfigMap can't be fetched.
        """
        self.terminal.step("Checking brig federation domain vs cluster domain...")

        _result, brig_cm = self.run_kubectl("configmap/brig")

        if not isinstance(brig_cm, dict):
            raise RuntimeError("Can't fetch brig ConfigMap")

        brig_yaml_str: str = brig_cm.get("data", {}).get("brig.yaml", "")

        if not brig_yaml_str:
            raise RuntimeError("brig ConfigMap missing brig.yaml")

        try:
            brig_config: dict[str, Any] = parse_yaml(brig_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Can't parse brig.yaml: {e}") from e

        # Try different key names (handles older formats too)
        brig_domain: str = str(
            get_nested(brig_config, "optSettings.setFederationDomain", "")
            or get_nested(brig_config, "setFederationDomain", "")
            or get_nested(brig_config, "federationDomain", "")
            or ""
        ).strip()

        cluster_domain: str = self.config.cluster.domain.strip()

        if not brig_domain:
            self._health_info = (
                f"Federation domain not set in brig (cluster: {cluster_domain}). "
                "Federation may not work correctly."
            )
            return False

        if not cluster_domain:
            self._health_info = (
                f"Cluster domain not configured, brig has: {brig_domain}"
            )
            return True

        matches: bool = brig_domain == cluster_domain

        if matches:
            self._health_info = (
                f"Federation domain matches: brig={brig_domain}, "
                f"cluster={cluster_domain}"
            )
        else:
            self._health_info = (
                f"MISMATCH: brig={brig_domain} vs cluster={cluster_domain}. "
                "Federation API calls will fail."
            )

        return matches
