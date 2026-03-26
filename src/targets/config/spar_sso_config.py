"""Reads SSO configuration from spar ConfigMap.

Extracts domain, appUri, and ssoUri to verify spar is configured correctly
for the cluster domain. Auto-detected — no user question.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class SparSsoConfig(BaseTarget):
    """Read SSO configuration from spar ConfigMap.

    Extracts domain, appUri, ssoUri. Runs always (auto-detection).
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Spar SSO configuration (domain, appUri, ssoUri)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Spar handles SAML SSO authentication. Its ssoUri and appUri must match "
            "the cluster domain for SSO login flows to work correctly."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read spar ConfigMap and extract SSO configuration.

        Returns:
            JSON string with spar SSO config details.

        Raises:
            RuntimeError: If spar ConfigMap can't be fetched or parsed.
        """
        self.terminal.step("Reading spar ConfigMap for SSO configuration...")

        _result, cm_data = self.run_kubectl("configmap/spar")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Cannot fetch spar ConfigMap")

        spar_yaml_str: str = cm_data.get("data", {}).get("spar.yaml", "")
        if not spar_yaml_str:
            raise RuntimeError("spar ConfigMap missing spar.yaml")

        try:
            spar_config: dict[str, Any] = parse_yaml(spar_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Cannot parse spar.yaml: {e}") from e

        spar_domain: str = str(get_nested(spar_config, "domain", "") or "")
        app_uri: str = str(get_nested(spar_config, "appUri", "") or "")
        sso_uri: str = str(get_nested(spar_config, "ssoUri", "") or "")
        max_scim_tokens: Any = get_nested(spar_config, "maxScimTokens", None)

        result: dict[str, Any] = {
            "domain": spar_domain,
            "app_uri": app_uri,
            "sso_uri": sso_uri,
            "max_scim_tokens": int(max_scim_tokens) if max_scim_tokens is not None else None,
        }

        self._health_info = f"Spar domain: {spar_domain}, ssoUri: {sso_uri}"

        return json.dumps(result)
