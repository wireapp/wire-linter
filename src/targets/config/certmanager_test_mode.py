"""Checks cert-manager isn't in test mode.

Test mode = Let's Encrypt staging certificates, browsers reject them.
Easy to forget to flip this after initial testing.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class CertmanagerTestMode(BaseTarget):
    """Checks cert-manager isn't in test mode.

    Looks at ClusterIssuers and ingress annotations for staging indicators.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Cert-manager not in test mode"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Test mode = Let's Encrypt staging, browsers reject the certs. "
            "Healthy when all issuers use production ACME servers."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check if cert-manager is using test certificates.

        Returns:
            True if production, False if test mode.
        """
        self.terminal.step("Checking cert-manager test mode...")

        _result, issuer_data = self.run_kubectl(
            "clusterissuers.cert-manager.io",
            all_namespaces=True,
        )

        is_test_mode: bool = False
        test_indicators: list[str] = []

        if isinstance(issuer_data, dict):
            items: list[dict[str, Any]] = issuer_data.get("items", [])

            for item in items:
                name: str = item.get("metadata", {}).get("name", "")
                spec: dict[str, Any] = item.get("spec", {})
                acme: dict[str, Any] = spec.get("acme", {})
                server: str = acme.get("server", "")

                if "staging" in server.lower():
                    is_test_mode = True
                    test_indicators.append(f"Issuer «{name}» uses staging")

        # Check ingress annotations too
        _result2, ingress_data = self.run_kubectl("ingress", all_namespaces=True)

        if isinstance(ingress_data, dict):
            for item in ingress_data.get("items", []):
                annotations: dict[str, str] = item.get("metadata", {}).get("annotations", {})
                ingress_name: str = item.get("metadata", {}).get("name", "")

                for key, value in annotations.items():
                    if "issuer" in key.lower() and "staging" in value.lower():
                        is_test_mode = True
                        test_indicators.append(
                            f"Ingress «{ingress_name}» references staging issuer"
                        )

        not_test_mode: bool = not is_test_mode

        if not_test_mode:
            self._health_info = "Cert-manager is using production certificates"
        else:
            self._health_info = f"TEST MODE: {'; '.join(test_indicators)}"

        return not_test_mode
