"""Checks that webapp config doesn't still point to placeholder URLs.

This is one of the most common reasons for « ERROR 6 » after a fresh
install. Verifies the webapp ConfigMap doesn't contain example.com or
other placeholder values.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Patterns that definitely indicate unconfigured placeholder values
_ERROR_PATTERNS: list[str] = [
    "example.com",
    "placeholder",
    "CHANGE_ME",
    "changeme",
]

# Patterns that might be legitimate in single-node or co-located deployments
# (e.g., local Redis sidecar, co-located Elasticsearch), but could also
# indicate an incomplete configuration
_WARNING_PATTERNS: list[str] = [
    "localhost",
    "127.0.0.1",
]


class WebappBackendUrls(BaseTarget):
    """Checks webapp config for placeholder backend URLs.

    Fetches the webapp deployment or ConfigMap and makes sure backend
    URLs aren't still set to placeholder values.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Webapp backend URLs not placeholder values"

    @property
    def explanation(self) -> str:
        """Why we're checking and what's healthy vs unhealthy."""
        return (
            "Placeholder URLs (example.com, CHANGE_ME) left in webapp config cause "
            "« ERROR 6 » on login. Localhost/127.0.0.1 URLs are flagged as warnings "
            "since they may be valid in single-node or co-located deployments."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty, result is boolean)."""
        return ""

    def collect(self) -> str | None:
        """Check webapp config for placeholder URLs.

        Returns:
            "ok" if no placeholder patterns found,
            "error" if definite placeholder patterns found (example.com, CHANGE_ME),
            "warning" if only localhost/127.0.0.1 found (may be legitimate),
            None if the webapp configuration could not be retrieved.
        """
        self.terminal.step("Checking webapp backend URLs...")

        # Try to get the webapp ConfigMap or deployment env vars
        _result, cm_data = self.run_kubectl("configmap/webapp")

        config_text: str = ""

        if isinstance(cm_data, dict):
            # Join all data keys together so we can search them
            data_section: dict[str, str] = cm_data.get("data", {})
            config_text = "\n".join(data_section.values())

        # Also check the deployment environment variables
        if not config_text:
            _result2, deploy_data = self.run_kubectl("deployment/webapp")
            if isinstance(deploy_data, dict):
                containers: list[dict[str, Any]] = (
                    deploy_data.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("containers", [])
                )
                for container in containers:
                    for env in container.get("env", []):
                        env_val: str = str(env.get("value", ""))
                        config_text += f"\n{env.get('name', '')}={env_val}"

        if not config_text:
            self._health_info = "Could not retrieve webapp configuration"
            return None  # Couldn't run the check

        config_lower: str = config_text.lower()

        # Check for definite placeholder patterns first
        found_errors: list[str] = []
        for pattern in _ERROR_PATTERNS:
            if pattern.lower() in config_lower:
                for line in config_text.split("\n"):
                    if pattern.lower() in line.lower():
                        found_errors.append(line.strip()[:80])
                        break

        if found_errors:
            self._health_info = (
                f"Placeholder URLs found: {'; '.join(found_errors[:3])}"
            )
            return "error"

        # Check for localhost/loopback patterns (may be legitimate)
        found_warnings: list[str] = []
        for pattern in _WARNING_PATTERNS:
            if pattern.lower() in config_lower:
                for line in config_text.split("\n"):
                    if pattern.lower() in line.lower():
                        found_warnings.append(line.strip()[:80])
                        break

        if found_warnings:
            self._health_info = (
                f"Localhost URLs found (may be valid): "
                f"{'; '.join(found_warnings[:3])}"
            )
            return "warning"

        self._health_info = "No placeholder URLs detected"
        return "ok"
