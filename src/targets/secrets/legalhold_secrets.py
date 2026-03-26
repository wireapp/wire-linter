"""Checks for existence of legal hold secrets in Kubernetes.

Legal hold requires: serviceToken, TLS certificate, TLS key. We check
existence only, not the actual secret values.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class LegalholdSecrets(BaseTarget):
    """Check if legalhold Kubernetes secrets exist.

    Only runs when expect_legalhold is true.
    """

    # Main-cluster target
    cluster_affinity: str = 'main'

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Legal hold secrets presence"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Legal hold requires a service token, TLS certificate, and TLS key "
            "stored as Kubernetes secrets. Without these, the legalhold service "
            "cannot authenticate with the Wire backend."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check for legalhold-related secrets.

        Returns:
            JSON string with secret existence details.

        Raises:
            NotApplicableError: If legal hold is not expected.
        """
        if not self.config.options.expect_legalhold:
            raise NotApplicableError("Legal hold is not enabled")

        self.terminal.step("Checking for legal hold secrets...")

        _result, data = self.run_kubectl("secrets")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch secret list")

        items: list[dict[str, Any]] = data.get("items", [])

        # Search for secrets that match legalhold patterns
        service_token_exists: bool = False
        tls_cert_exists: bool = False
        tls_key_exists: bool = False

        for secret in items:
            name: str = secret.get("metadata", {}).get("name", "")
            data_keys: list[str] = list(secret.get("data", {}).keys())

            if "legalhold" in name.lower() or "legal-hold" in name.lower():
                for key in data_keys:
                    key_lower: str = key.lower()
                    if "token" in key_lower or "service" in key_lower:
                        service_token_exists = True
                    if "cert" in key_lower or "crt" in key_lower:
                        tls_cert_exists = True
                    if "key" in key_lower and "cert" not in key_lower:
                        tls_key_exists = True

        result: dict[str, Any] = {
            "service_token_exists": service_token_exists,
            "tls_cert_exists": tls_cert_exists,
            "tls_key_exists": tls_key_exists,
        }

        found: list[str] = []
        missing: list[str] = []
        if service_token_exists:
            found.append("token")
        else:
            missing.append("token")
        if tls_cert_exists:
            found.append("cert")
        else:
            missing.append("cert")
        if tls_key_exists:
            found.append("key")
        else:
            missing.append("key")

        if not missing:
            self._health_info = "All legalhold secrets found"
        else:
            self._health_info = f"Legalhold secrets: found={', '.join(found) or 'none'}, missing={', '.join(missing)}"

        return json.dumps(result)
