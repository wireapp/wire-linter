"""Reads federation+calling settings from brig ConfigMap.

When both federation and calling are enabled, brig needs:
- multiSFT.enabled: true (top-level, enables SFT-to-SFT communication)
- setSftListAllServers: "enabled" (so clients discover all SFT servers)

These are separate from the regular calling config because they only matter
for federated conference calls.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class FederationCallingBrig(BaseTarget):
    """Read federation+calling settings from brig ConfigMap.

    Only runs when both federation and calling are expected.
    """

    # Main-cluster target (brig is in the main cluster)
    cluster_affinity: str = 'main'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federation calling settings in brig (multiSFT, setSftListAllServers)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federated conference calls require multiSFT.enabled: true in brig "
            "(for SFT-to-SFT communication between federated backends) and "
            "setSftListAllServers: 'enabled' (so clients discover all SFT servers)."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read brig ConfigMap and extract federation calling settings.

        Returns:
            JSON string with federation calling config.

        Raises:
            NotApplicableError: If federation or calling is not expected.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled")

        self.terminal.step("Reading brig ConfigMap for federation calling settings...")

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

        # multiSFT is a top-level config (NOT inside optSettings)
        raw_multi_sft: Any = get_nested(brig_config, "multiSFT", None)
        multi_sft_enabled: bool = False
        if isinstance(raw_multi_sft, dict):
            multi_sft_enabled = bool(raw_multi_sft.get("enabled", False))
        elif isinstance(raw_multi_sft, bool):
            multi_sft_enabled = raw_multi_sft

        # setSftListAllServers is inside optSettings
        sft_list_all: str = str(
            get_nested(brig_config, "optSettings.setSftListAllServers", "") or ""
        )

        result: dict[str, Any] = {
            "multi_sft_enabled": multi_sft_enabled,
            "sft_list_all_servers": sft_list_all,
        }

        parts: list[str] = []
        parts.append(f"multiSFT: {'enabled' if multi_sft_enabled else 'DISABLED'}")
        parts.append(f"setSftListAllServers: '{sft_list_all or 'not set'}'")
        self._health_info = ", ".join(parts)

        return json.dumps(result)
