"""Detects SSO (SAML) feature flag from galley ConfigMap.

Julia said: "The thing that we should notice is whether SSO is even allowed,
because there's like some stupid flag you have to go turn on for SSO to be
available." The flag is settings.featureFlags.sso in galley's config.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class GalleySsoFlag(BaseTarget):
    """Detect SSO feature flag from galley ConfigMap.

    Reads settings.featureFlags.sso to determine if SSO is enabled.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Galley SSO feature flag"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "SSO (SAML authentication via spar) must be enabled in galley's feature flags. "
            "The sso flag should be 'enabled-by-default' for SSO to work. "
            "If it's disabled, users cannot authenticate via their identity provider."
        )

    @property
    def unit(self) -> str:
        """No unit — returns the flag value as a string."""
        return ""

    def collect(self) -> str:
        """Read galley ConfigMap and extract the SSO feature flag.

        Returns:
            The SSO feature flag value (e.g. "enabled-by-default").

        Raises:
            RuntimeError: If galley ConfigMap can't be fetched or parsed.
        """
        self.terminal.step("Reading galley ConfigMap for SSO feature flag...")

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

        # The SSO flag lives in settings.featureFlags.sso
        sso_flag: Any = (
            get_nested(galley_config, "settings.featureFlags.sso")
            or get_nested(galley_config, "featureFlags.sso")
            or ""
        )

        sso_value: str = str(sso_flag) if sso_flag else "not set"

        if "enabled" in sso_value.lower():
            self._health_info = f"SSO is enabled (flag: {sso_value})"
        elif sso_value == "not set":
            self._health_info = "SSO feature flag is not set in galley config"
        else:
            self._health_info = f"SSO is disabled (flag: {sso_value})"

        return sso_value
