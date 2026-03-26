"""Reads calling configuration from brig ConfigMap.

Extracts TURN server URIs (turnStatic.v2), SFT URL (setSftStaticUrl),
setSftListAllServers, and multiSFT settings. These are essential for
verifying that calling infrastructure is properly configured.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class BrigCallingConfig(BaseTarget):
    """Read calling configuration from brig ConfigMap.

    Extracts TURN URIs, SFT URL, and federation calling settings.
    Only runs when expect_calling is true.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Calling configuration (TURN URIs, SFT URL)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire calling requires TURN server URIs for 1:1 calls (coturn) and an "
            "SFT URL for conference calls. If these are misconfigured or missing, "
            "calls will fail."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read brig ConfigMap and extract calling configuration.

        Returns:
            JSON string with calling config details.

        Raises:
            NotApplicableError: If calling is not expected.
            RuntimeError: If brig ConfigMap can't be fetched or parsed.
        """
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled in the deployment configuration")

        self.terminal.step("Reading brig ConfigMap for calling configuration...")

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

        # TURN server URIs for 1:1 calling (coturn)
        turn_v1: list[str] = []
        raw_v1: Any = get_nested(brig_config, "turnStatic.v1", [])
        if isinstance(raw_v1, list):
            turn_v1 = [str(u) for u in raw_v1 if u]

        turn_v2: list[str] = []
        raw_v2: Any = get_nested(brig_config, "turnStatic.v2", [])
        if isinstance(raw_v2, list):
            turn_v2 = [str(u) for u in raw_v2 if u]

        # SFT URL for conference calling
        sft_static_url: str = str(
            get_nested(brig_config, "optSettings.setSftStaticUrl", "") or ""
        )

        # setSftListAllServers (must be "enabled" for federation calling)
        sft_list_all_servers: str = str(
            get_nested(brig_config, "optSettings.setSftListAllServers", "") or ""
        )

        # multiSFT — top-level config (not inside optSettings)
        # Used for federated calling SFT-to-SFT communication
        raw_multi_sft: Any = get_nested(brig_config, "multiSFT", None)
        multi_sft_enabled: bool = False
        if isinstance(raw_multi_sft, dict):
            multi_sft_enabled = bool(raw_multi_sft.get("enabled", False))
        elif isinstance(raw_multi_sft, bool):
            multi_sft_enabled = raw_multi_sft

        # TURN secret configured (don't extract the value, just check presence)
        turn_secret_path: Any = get_nested(brig_config, "turn.secret", None)
        turn_secret_configured: bool = turn_secret_path is not None and str(turn_secret_path).strip() != ""

        result: dict[str, Any] = {
            "turn_v1_uris": turn_v1,
            "turn_v2_uris": turn_v2,
            "sft_static_url": sft_static_url,
            "sft_list_all_servers": sft_list_all_servers,
            "multi_sft_enabled": multi_sft_enabled,
            "turn_secret_configured": turn_secret_configured,
        }

        # Build health summary
        parts: list[str] = []
        parts.append(f"TURN v2: {len(turn_v2)} URI(s)")
        if sft_static_url:
            parts.append(f"SFT: {sft_static_url}")
        else:
            parts.append("SFT: not configured")
        if multi_sft_enabled:
            parts.append("multiSFT: enabled")

        self._health_info = ", ".join(parts)
        return json.dumps(result)
