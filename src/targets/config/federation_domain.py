"""Checks federation domain is consistent in brig and galley.

Must be identical when configured. Federation is optional for many deployments.
Note: different key names (brig: optSettings.setFederationDomain, galley: settings.federationDomain).
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class FederationDomain(BaseTarget):
    """Checks federation domain consistency between brig and galley.

    Fetches both ConfigMaps and compares values.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federation domain consistent in brig and galley"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federation domain must match in both services when federation is enabled. "
            "Not configured is normal for non-federation deployments."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool | str:
        """Compare federation domain between brig and galley.

        Returns:
            True if they match, False if mismatched/partially set,
            'not_configured' if neither service has a federation domain.

        Raises:
            RuntimeError: If ConfigMaps can't be fetched.
        """
        self.terminal.step("Checking federation domain consistency...")

        _result_brig, brig_cm = self.run_kubectl("configmap/brig")
        _result_galley, galley_cm = self.run_kubectl("configmap/galley")

        brig_domain: str = ""
        galley_domain: str = ""

        if isinstance(brig_cm, dict):
            brig_yaml_str: str = brig_cm.get("data", {}).get("brig.yaml", "")
            if brig_yaml_str:
                try:
                    brig_yaml: dict[str, Any] = parse_yaml(brig_yaml_str)
                    brig_domain = str(
                        get_nested(brig_yaml, "optSettings.setFederationDomain", "")
                        or get_nested(brig_yaml, "federationDomain", "")
                        or ""
                    )
                except (ValueError, TypeError):
                    pass

        if isinstance(galley_cm, dict):
            galley_yaml_str: str = galley_cm.get("data", {}).get("galley.yaml", "")
            if galley_yaml_str:
                try:
                    galley_yaml: dict[str, Any] = parse_yaml(galley_yaml_str)
                    galley_domain = str(
                        get_nested(galley_yaml, "settings.federationDomain", "")
                        or get_nested(galley_yaml, "federationDomain", "")
                        or ""
                    )
                except (ValueError, TypeError):
                    pass

        if not brig_domain and not galley_domain:
            # Federation is optional — return sentinel so UI checker can decide severity
            self._health_info = "Federation domain not configured in either service"
            return "not_configured"

        if not brig_domain:
            self._health_info = f"Federation domain missing in brig, galley has «{galley_domain}»"
            return False

        if not galley_domain:
            self._health_info = f"Federation domain missing in galley, brig has «{brig_domain}»"
            return False

        consistent: bool = brig_domain == galley_domain

        if consistent:
            self._health_info = f"Federation domain consistent: {brig_domain}"
        else:
            self._health_info = f"MISMATCH: brig=«{brig_domain}», galley=«{galley_domain}»"

        return consistent
