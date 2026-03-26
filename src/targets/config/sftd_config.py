"""Reads SFT (conference calling) deployment configuration.

Extracts SFT settings: host, allowOrigin, multiSFT config.
Only runs when calling and SFT are expected.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class SftdConfig(BaseTarget):
    """Read SFT deployment configuration.

    Looks for the sftd deployment/ConfigMap and extracts configuration.
    Only runs when calling and SFT are enabled.
    """

    # SFT is a calling-cluster target
    cluster_affinity: str = 'calling'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "SFT conference calling configuration"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The SFT (Selective Forwarding TURN) service handles conference calls. "
            "Its configuration must include the correct host domain, CORS allowOrigin, "
            "and (when federation is enabled) multiSFT settings."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read SFT configuration from the cluster.

        Returns:
            JSON string with SFT config details.

        Raises:
            NotApplicableError: If calling or SFT is not expected.
        """
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled")
        if not self.config.options.expect_sft:
            raise NotApplicableError("SFT (conference calling) is not enabled")

        self.terminal.step("Reading SFT configuration...")

        # Try to find the sftd ConfigMap
        found_in_cluster: bool = False
        host: str = ""
        allow_origin: str = ""
        multi_sft_enabled: bool = False
        multi_sft_turn_uri: str = ""
        replica_count: int = 0

        try:
            _result, cm_data = self.run_kubectl("configmap/sftd")
            if isinstance(cm_data, dict) and cm_data.get("data"):
                found_in_cluster = True
                # SFT config may be in various keys
                for key in cm_data.get("data", {}):
                    yaml_str: str = cm_data["data"][key]
                    try:
                        config: dict[str, Any] = parse_yaml(yaml_str)
                        host = str(get_nested(config, "host", "") or host)
                        allow_origin = str(get_nested(config, "allowOrigin", "") or allow_origin)
                        raw_multi: Any = get_nested(config, "multiSFT", None)
                        if isinstance(raw_multi, dict):
                            multi_sft_enabled = bool(raw_multi.get("enabled", False))
                            multi_sft_turn_uri = str(raw_multi.get("turnServerURI", ""))
                    except (ValueError, TypeError):
                        pass
        except RuntimeError:
            pass

        # If ConfigMap not found, try to get info from the deployment
        if not found_in_cluster:
            try:
                _result2, deploy_data = self.run_kubectl("deployment/sftd", output_format="json")
                if isinstance(deploy_data, dict):
                    found_in_cluster = True
                    spec: dict[str, Any] = deploy_data.get("spec", {})
                    replica_count = spec.get("replicas", 0)
            except RuntimeError:
                pass

        result: dict[str, Any] = {
            "found_in_cluster": found_in_cluster,
            "host": host,
            "allow_origin": allow_origin,
            "multi_sft_enabled": multi_sft_enabled,
            "multi_sft_turn_uri": multi_sft_turn_uri,
            "replica_count": replica_count,
        }

        if not found_in_cluster:
            if self.config.options.calling_in_dmz:
                self._health_info = "SFT not found in main cluster (expected in DMZ cluster)"
            else:
                self._health_info = "SFT deployment/ConfigMap not found in the cluster"
        else:
            self._health_info = f"SFT found: host={host or 'not set'}, multiSFT={'enabled' if multi_sft_enabled else 'disabled'}"

        return json.dumps(result)
