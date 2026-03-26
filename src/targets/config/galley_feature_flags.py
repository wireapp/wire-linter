"""Checks galley has all mandatory feature flag keys.

Missing one key = CrashLoopBackOff with AesonException.
Required: sso, legalhold, teamSearchVisibility, mls, mlsMigration.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


# Feature flags that galley requires to be set
_REQUIRED_FLAGS: list[str] = [
    "sso",
    "legalhold",
    "teamSearchVisibility",
    "mls",
    "mlsMigration",
]


class GalleyFeatureFlags(BaseTarget):
    """Checks galley for mandatory feature flags.

    Fetches galley ConfigMap and verifies all required flags are present.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Galley feature flags completeness"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Missing any flag = CrashLoopBackOff with AesonException. "
            "Healthy when all flags present."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check galley for required feature flags.

        Returns:
            True if all flags present, False otherwise.

        Raises:
            RuntimeError: If galley ConfigMap can't be fetched.
        """
        self.terminal.step("Checking galley feature flags...")

        _result, cm_data = self.run_kubectl("configmap/galley")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Can't fetch galley ConfigMap")

        galley_yaml_str: str = cm_data.get("data", {}).get("galley.yaml", "")

        if not galley_yaml_str:
            raise RuntimeError("galley ConfigMap missing galley.yaml")

        try:
            galley_config: dict[str, Any] = parse_yaml(galley_yaml_str)
        except ValueError:
            raise RuntimeError("Can't parse galley.yaml")

        # Feature flags may be nested
        feature_flags: dict[str, Any] = (
            get_nested(galley_config, "settings.featureFlags")
            or get_nested(galley_config, "featureFlags")
            or {}
        )

        if not isinstance(feature_flags, dict):
            feature_flags = {}

        present: list[str] = []
        missing: list[str] = []

        for flag in _REQUIRED_FLAGS:
            if flag in feature_flags:
                present.append(flag)
            else:
                missing.append(flag)

        all_present: bool = len(missing) == 0

        if all_present:
            self._health_info = f"All {len(_REQUIRED_FLAGS)} required flags present"
        else:
            self._health_info = f"Missing flags: {', '.join(missing)}"

        return all_present
