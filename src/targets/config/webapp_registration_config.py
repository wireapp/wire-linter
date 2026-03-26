"""Detects webapp registration UI settings from webapp ConfigMap.

Reads FEATURE_ENABLE_ACCOUNT_REGISTRATION and FEATURE_ENABLE_SSO environment
variables from the webapp ConfigMap. Cross-referenced with brig's registration
settings to detect inconsistencies (e.g. backend blocks registration but webapp
still shows the form).
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class WebappRegistrationConfig(BaseTarget):
    """Detect webapp registration UI settings from ConfigMap.

    Reads FEATURE_ENABLE_ACCOUNT_REGISTRATION and FEATURE_ENABLE_SSO from
    the webapp deployment's environment variables.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Webapp registration UI settings"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The webapp can show or hide the registration form independently from "
            "whether brig actually accepts registrations. If these are inconsistent, "
            "users see a form but registration fails — confusing."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read webapp ConfigMap or deployment for registration settings.

        Returns:
            JSON string with webapp registration UI config.

        Raises:
            RuntimeError: If webapp config can't be read.
        """
        self.terminal.step("Reading webapp configuration for registration settings...")

        # The webapp config is stored as environment variables in the deployment
        # or as a ConfigMap. Try ConfigMap first, then deployment env vars.
        account_registration: str = ""
        sso_enabled: str = ""

        # Try reading from webapp ConfigMap
        _result, cm_data = self.run_kubectl("configmap/webapp")
        if isinstance(cm_data, dict):
            data_section: dict[str, str] = cm_data.get("data", {})
            account_registration = data_section.get("FEATURE_ENABLE_ACCOUNT_REGISTRATION", "")
            sso_enabled = data_section.get("FEATURE_ENABLE_SSO", "")

        # If ConfigMap didn't have it, try reading from the deployment's env vars
        if not account_registration:
            _result2, deploy_data = self.run_kubectl("deployment/webapp", output_format="json")
            if isinstance(deploy_data, dict):
                containers: list[dict[str, Any]] = (
                    deploy_data.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("containers", [])
                )
                for container in containers:
                    for env_var in container.get("env", []):
                        name: str = env_var.get("name", "")
                        value: str = str(env_var.get("value", ""))
                        if name == "FEATURE_ENABLE_ACCOUNT_REGISTRATION":
                            account_registration = value
                        elif name == "FEATURE_ENABLE_SSO":
                            sso_enabled = value

        result: dict[str, Any] = {
            "account_registration_enabled": account_registration.lower() == "true",
            "sso_enabled": sso_enabled.lower() == "true",
            "raw_account_registration": account_registration,
            "raw_sso_enabled": sso_enabled,
        }

        self._health_info = (
            f"Registration form: {'shown' if result['account_registration_enabled'] else 'hidden'}, "
            f"SSO: {'enabled' if result['sso_enabled'] else 'disabled'}"
        )

        return json.dumps(result)
