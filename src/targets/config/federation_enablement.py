"""Checks enableFederation flag across all four Wire services.

Federation requires enableFederation: true in brig, galley, cargohold, and
background-worker. If any service is missing the flag, federation is partially
broken. This target checks all four and reports which are enabled.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


# The four services that need enableFederation to be set
_FEDERATION_SERVICES: list[dict[str, str]] = [
    {"name": "brig",              "configmap": "configmap/brig",              "yaml_key": "brig.yaml",              "path": "enableFederation"},
    {"name": "galley",            "configmap": "configmap/galley",            "yaml_key": "galley.yaml",            "path": "enableFederation"},
    {"name": "cargohold",         "configmap": "configmap/cargohold",         "yaml_key": "cargohold.yaml",         "path": "enableFederation"},
    {"name": "background-worker", "configmap": "configmap/background-worker", "yaml_key": "background-worker.yaml", "path": "enableFederation"},
]


class FederationEnablement(BaseTarget):
    """Check enableFederation flag in brig, galley, cargohold, background-worker.

    Returns a structured result showing which services have federation enabled.
    This target runs even when expect_federation is false — so we can detect
    stray enablement and warn about inconsistency.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federation enablement across brig, galley, cargohold, background-worker"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federation requires enableFederation: true in all four services "
            "(brig, galley, cargohold, background-worker). If any service has it "
            "disabled while others have it enabled, federation is partially broken."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check enableFederation in all four service ConfigMaps.

        Returns:
            JSON string with per-service enablement status.

        Raises:
            RuntimeError: If any ConfigMap can't be fetched.
        """
        self.terminal.step("Checking enableFederation across Wire services...")

        results: dict[str, bool | None] = {}

        for service in _FEDERATION_SERVICES:
            service_name: str = service["name"]
            self.terminal.step(f"  Checking {service_name}...")

            try:
                _result, cm_data = self.run_kubectl(service["configmap"])

                if not isinstance(cm_data, dict):
                    results[service_name] = None
                    continue

                yaml_str: str = cm_data.get("data", {}).get(service["yaml_key"], "")
                if not yaml_str:
                    results[service_name] = None
                    continue

                config: dict[str, Any] = parse_yaml(yaml_str)
                flag_value: Any = get_nested(config, service["path"], False)
                results[service_name] = bool(flag_value)
            except (RuntimeError, ValueError):
                # ConfigMap couldn't be read or parsed
                results[service_name] = None

        # Compute aggregate flags
        non_null_values: list[bool] = [v for v in results.values() if v is not None]
        all_enabled: bool = len(non_null_values) > 0 and all(non_null_values)
        all_disabled: bool = len(non_null_values) > 0 and not any(non_null_values)

        output: dict[str, Any] = {
            **results,
            "all_enabled": all_enabled,
            "all_disabled": all_disabled,
        }

        # Build health summary
        enabled_services: list[str] = [k for k, v in results.items() if v is True]
        disabled_services: list[str] = [k for k, v in results.items() if v is False]
        unknown_services: list[str] = [k for k, v in results.items() if v is None]

        if all_enabled:
            self._health_info = "Federation enabled in all 4 services"
        elif all_disabled:
            self._health_info = "Federation disabled in all services"
        else:
            parts: list[str] = []
            if enabled_services:
                parts.append(f"enabled: {', '.join(enabled_services)}")
            if disabled_services:
                parts.append(f"disabled: {', '.join(disabled_services)}")
            if unknown_services:
                parts.append(f"unknown: {', '.join(unknown_services)}")
            self._health_info = f"Federation inconsistent — {'; '.join(parts)}"

        return json.dumps(output)
