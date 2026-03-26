"""Reads coturn federation settings for federated calling.

When federation + calling are both enabled, coturn needs federate.enabled: true
and a dedicated federation port (default 9191) for DTLS.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class FederationCallingCoturn(BaseTarget):
    """Read coturn federation settings.

    Only runs when federation and calling are both expected.
    """

    # Coturn is in the calling cluster
    cluster_affinity: str = 'calling'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Coturn federation calling configuration"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federated calling may require coturn to handle DTLS connections between "
            "SFT servers of different federated backends. Coturn needs "
            "federate.enabled: true and a dedicated federation port."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read coturn federation config from the cluster.

        Returns:
            JSON string with coturn federation config.

        Raises:
            NotApplicableError: If prerequisites not met.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled")

        self.terminal.step("Reading coturn federation configuration...")

        found_in_cluster: bool = False
        federate_enabled: bool = False
        federate_port: int = 0
        dtls_enabled: bool = False
        federation_listening_ip: str = ""

        # Try to read coturn ConfigMap
        try:
            _result, cm_data = self.run_kubectl("configmap/coturn")
            if isinstance(cm_data, dict) and cm_data.get("data"):
                found_in_cluster = True
                for key in cm_data.get("data", {}):
                    yaml_str: str = cm_data["data"][key]
                    try:
                        config: dict[str, Any] = parse_yaml(yaml_str)
                        raw_fed: Any = get_nested(config, "federate", None)
                        if isinstance(raw_fed, dict):
                            federate_enabled = bool(raw_fed.get("enabled", False))
                            federate_port = int(raw_fed.get("port", 0) or 0)
                            raw_dtls: Any = raw_fed.get("dtls", {})
                            if isinstance(raw_dtls, dict):
                                dtls_enabled = bool(raw_dtls.get("enabled", False))
                        federation_listening_ip = str(
                            get_nested(config, "coturnFederationListeningIP", "") or ""
                        )
                    except (ValueError, TypeError):
                        pass
        except RuntimeError:
            pass

        # If ConfigMap not found, check for deployment
        if not found_in_cluster:
            try:
                _result2, deploy = self.run_kubectl("deployment/coturn", output_format="json")
                if isinstance(deploy, dict):
                    found_in_cluster = True
            except RuntimeError:
                pass
            # Also try statefulset (coturn may be a StatefulSet)
            if not found_in_cluster:
                try:
                    _result3, sts = self.run_kubectl("statefulset/coturn", output_format="json")
                    if isinstance(sts, dict):
                        found_in_cluster = True
                except RuntimeError:
                    pass

        result: dict[str, Any] = {
            "found_in_cluster": found_in_cluster,
            "federate_enabled": federate_enabled,
            "federate_port": federate_port,
            "dtls_enabled": dtls_enabled,
            "federation_listening_ip": federation_listening_ip,
        }

        if not found_in_cluster:
            if self.config.options.calling_in_dmz:
                self._health_info = "Coturn not found (expected in DMZ calling cluster)"
            else:
                self._health_info = "Coturn not found in cluster"
        else:
            self._health_info = (
                f"Coturn federation: {'enabled' if federate_enabled else 'DISABLED'}"
                f"{f', port {federate_port}' if federate_port else ''}"
                f"{', DTLS enabled' if dtls_enabled else ''}"
            )

        return json.dumps(result)
