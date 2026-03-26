"""Reads SFT federation settings for federated conference calling.

When federation + calling + SFT are all enabled, the SFT deployment needs
multiSFT.enabled: true, a turnServerURI, and a shared secret.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class FederationCallingSft(BaseTarget):
    """Read SFT federation calling settings.

    Only runs when federation, calling, and SFT are all expected.
    """

    # SFT is in the calling cluster
    cluster_affinity: str = 'calling'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "SFT federation calling configuration (multiSFT)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federated conference calls require SFT-to-SFT communication between "
            "backends. The SFT chart must have multiSFT.enabled: true, a turnServerURI "
            "for relay, and a shared secret."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read SFT federation config from the cluster.

        Returns:
            JSON string with SFT federation calling config.

        Raises:
            NotApplicableError: If prerequisites not met.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled")
        if not self.config.options.expect_sft:
            raise NotApplicableError("SFT is not enabled")

        self.terminal.step("Reading SFT federation calling configuration...")

        found_in_cluster: bool = False
        multi_sft_enabled: bool = False
        turn_server_uri: str = ""
        secret_configured: bool = False

        # Try to read the sftd ConfigMap
        try:
            _result, cm_data = self.run_kubectl("configmap/sftd")
            if isinstance(cm_data, dict) and cm_data.get("data"):
                found_in_cluster = True
                for key in cm_data.get("data", {}):
                    yaml_str: str = cm_data["data"][key]
                    try:
                        config: dict[str, Any] = parse_yaml(yaml_str)
                        raw_multi: Any = get_nested(config, "multiSFT", None)
                        if isinstance(raw_multi, dict):
                            multi_sft_enabled = bool(raw_multi.get("enabled", False))
                            turn_server_uri = str(raw_multi.get("turnServerURI", ""))
                            secret_val: Any = raw_multi.get("secret", None)
                            secret_configured = secret_val is not None and str(secret_val).strip() != ""
                    except (ValueError, TypeError):
                        pass
        except RuntimeError:
            pass

        # If not found via ConfigMap, check if sftd deployment exists at all
        if not found_in_cluster:
            try:
                _result2, deploy = self.run_kubectl("deployment/sftd", output_format="json")
                if isinstance(deploy, dict):
                    found_in_cluster = True
            except RuntimeError:
                pass

        result: dict[str, Any] = {
            "found_in_cluster": found_in_cluster,
            "multi_sft_enabled": multi_sft_enabled,
            "turn_server_uri": turn_server_uri,
            "secret_configured": secret_configured,
        }

        if not found_in_cluster:
            if self.config.options.calling_in_dmz:
                self._health_info = "SFT not found (expected in DMZ calling cluster)"
            else:
                self._health_info = "SFT not found in cluster"
        else:
            self._health_info = (
                f"SFT multiSFT: {'enabled' if multi_sft_enabled else 'DISABLED'}, "
                f"TURN URI: '{turn_server_uri or 'not set'}', "
                f"secret: {'yes' if secret_configured else 'NO'}"
            )

        return json.dumps(result)
