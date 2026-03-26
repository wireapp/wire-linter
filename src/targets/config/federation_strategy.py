"""Reads federation strategy and domain configs from brig ConfigMap.

The federation strategy (allowNone/allowAll/allowDynamic) controls which
backends this instance will federate with. When using allowDynamic, the
setFederationDomainConfigs list must contain entries for each partner.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class FederationStrategy(BaseTarget):
    """Read federation strategy and domain configs from brig.

    Only runs when expect_federation is true in the deployment configuration.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federation strategy and domain configuration"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The federation strategy controls which backends are allowed to federate. "
            "'allowNone' (default) effectively disables federation even when "
            "enableFederation is true. 'allowAll' federates with any reachable backend. "
            "'allowDynamic' federates only with explicitly listed domains."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read brig ConfigMap and extract federation strategy settings.

        Returns:
            JSON string with strategy details.

        Raises:
            NotApplicableError: If federation is not expected.
            RuntimeError: If brig ConfigMap can't be fetched or parsed.
        """
        # Only run when federation is expected
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled in the deployment configuration")

        self.terminal.step("Reading brig ConfigMap for federation strategy...")

        _result, cm_data = self.run_kubectl("configmap/brig")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Cannot fetch brig ConfigMap")

        brig_yaml_str: str = cm_data.get("data", {}).get("brig.yaml", "")
        if not brig_yaml_str:
            raise RuntimeError("brig ConfigMap missing brig.yaml")

        try:
            brig_config: dict[str, Any] = parse_yaml(brig_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Cannot parse brig.yaml: {e}") from e

        # Extract federation strategy
        strategy: str = str(
            get_nested(brig_config, "optSettings.setFederationStrategy", "allowNone")
            or "allowNone"
        )

        # Extract federation domain configs (list of {domain, search_policy})
        raw_domain_configs: Any = get_nested(
            brig_config, "optSettings.setFederationDomainConfigs", []
        )
        domain_configs: list[dict[str, str]] = []
        if isinstance(raw_domain_configs, list):
            for entry in raw_domain_configs:
                if isinstance(entry, dict):
                    domain_configs.append({
                        "domain": str(entry.get("domain", "")),
                        "search_policy": str(entry.get("search_policy", "")),
                    })

        # Extract this backend's own federation domain
        federation_domain: str = str(
            get_nested(brig_config, "optSettings.setFederationDomain", "") or ""
        )

        result: dict[str, Any] = {
            "strategy": strategy,
            "domain_configs": domain_configs,
            "federation_domain": federation_domain,
            "configured_domains": [c["domain"] for c in domain_configs],
        }

        self._health_info = (
            f"Strategy: {strategy}, "
            f"domain: {federation_domain}, "
            f"partners: {len(domain_configs)}"
        )

        return json.dumps(result)
