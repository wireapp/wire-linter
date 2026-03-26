"""Reads the legal hold feature flag from galley ConfigMap.

Legal hold requires galley's legalhold feature flag to be set to
'disabled-by-default' (not the default 'disabled-permanently').
'disabled-permanently' means legal hold can never be activated.
'disabled-by-default' means it can be enabled per-team.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class GalleyLegalholdFlag(BaseTarget):
    """Read the legal hold feature flag from galley ConfigMap.

    Only runs when expect_legalhold is true.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Galley legal hold feature flag"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Legal hold records communications for compliance. The galley feature flag "
            "must be 'disabled-by-default' (opt-in per team) rather than the default "
            "'disabled-permanently' (blocks legal hold entirely)."
        )

    @property
    def unit(self) -> str:
        """No unit — returns the flag value as a string."""
        return ""

    def collect(self) -> str:
        """Read galley ConfigMap and extract the legal hold feature flag.

        Returns:
            The legalhold feature flag value string.

        Raises:
            NotApplicableError: If legal hold is not expected.
            RuntimeError: If galley ConfigMap can't be fetched or parsed.
        """
        if not self.config.options.expect_legalhold:
            raise NotApplicableError("Legal hold is not enabled in the deployment configuration")

        self.terminal.step("Reading galley ConfigMap for legal hold feature flag...")

        _result, cm_data = self.run_kubectl("configmap/galley")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Cannot fetch galley ConfigMap")

        galley_yaml_str: str = cm_data.get("data", {}).get("galley.yaml", "")
        if not galley_yaml_str:
            raise RuntimeError("galley ConfigMap missing galley.yaml")

        try:
            galley_config: dict[str, Any] = parse_yaml(galley_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Cannot parse galley.yaml: {e}") from e

        legalhold_flag: Any = (
            get_nested(galley_config, "settings.featureFlags.legalhold")
            or get_nested(galley_config, "featureFlags.legalhold")
            or ""
        )

        flag_value: str = str(legalhold_flag) if legalhold_flag else "not set"

        if flag_value == "disabled-by-default":
            self._health_info = "Legal hold can be activated per-team (disabled-by-default)"
        elif flag_value == "disabled-permanently":
            self._health_info = "Legal hold is permanently disabled — cannot be activated"
        elif flag_value == "not set":
            self._health_info = "Legal hold feature flag not set (defaults to disabled-permanently)"
        else:
            self._health_info = f"Legal hold flag: {flag_value}"

        return flag_value
