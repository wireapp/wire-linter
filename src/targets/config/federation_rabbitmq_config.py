"""Checks RabbitMQ host configuration across services that need it for federation.

Federation requires RabbitMQ for async event processing. Brig, galley, cannon, and
background-worker all need rabbitmq.host configured. If any service is missing it,
federation events won't be processed.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


# Services that need rabbitmq.host for federation
_RABBITMQ_SERVICES: list[dict[str, str]] = [
    {"name": "brig",              "configmap": "configmap/brig",              "yaml_key": "brig.yaml"},
    {"name": "galley",            "configmap": "configmap/galley",            "yaml_key": "galley.yaml"},
    {"name": "cannon",            "configmap": "configmap/cannon",            "yaml_key": "cannon.yaml"},
    {"name": "background-worker", "configmap": "configmap/background-worker", "yaml_key": "background-worker.yaml"},
]


class FederationRabbitmqConfig(BaseTarget):
    """Check rabbitmq.host is configured in all services that need it for federation.

    Only runs when expect_federation is true.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "RabbitMQ host configured in brig, galley, cannon, background-worker"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federation depends on RabbitMQ for async event processing. All four "
            "services (brig, galley, cannon, background-worker) must have a valid "
            "rabbitmq.host configured."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check rabbitmq.host in all relevant service ConfigMaps.

        Returns:
            JSON string with per-service RabbitMQ host values.

        Raises:
            NotApplicableError: If federation is not expected.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled in the deployment configuration")

        self.terminal.step("Checking RabbitMQ host configuration for federation...")

        results: dict[str, str] = {}

        for service in _RABBITMQ_SERVICES:
            service_name: str = service["name"]
            self.terminal.step(f"  Checking {service_name}...")

            try:
                _result, cm_data = self.run_kubectl(service["configmap"])

                if not isinstance(cm_data, dict):
                    results[service_name] = ""
                    continue

                yaml_str: str = cm_data.get("data", {}).get(service["yaml_key"], "")
                if not yaml_str:
                    results[service_name] = ""
                    continue

                config: dict[str, Any] = parse_yaml(yaml_str)
                rmq_host: str = str(get_nested(config, "rabbitmq.host", "") or "")
                results[service_name] = rmq_host
            except (RuntimeError, ValueError):
                results[service_name] = ""

        all_configured: bool = all(v != "" for v in results.values())

        output: dict[str, Any] = {
            **results,
            "all_configured": all_configured,
        }

        if all_configured:
            # All point to the same host? Note it.
            unique_hosts: set[str] = set(results.values())
            if len(unique_hosts) == 1:
                self._health_info = f"All services use RabbitMQ at {unique_hosts.pop()}"
            else:
                self._health_info = f"RabbitMQ configured in all services (hosts: {', '.join(unique_hosts)})"
        else:
            missing: list[str] = [k for k, v in results.items() if v == ""]
            self._health_info = f"RabbitMQ NOT configured in: {', '.join(missing)}"

        return json.dumps(output)
