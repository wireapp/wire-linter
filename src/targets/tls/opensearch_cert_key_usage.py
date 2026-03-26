"""Checks TLS certificate key usage extensions on the OpenSearch endpoint.

Certs without correct keyUsage (digitalSignature + keyEncipherment) and
extendedKeyUsage (serverAuth) are rejected by strict TLS clients. Java's
TLS stack in OpenSearch plugins enforces these. Missing extensions cause
«Remote end closed connection» errors from Elasticsearch/OpenSearch clients.
See WPB-18068.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


# TLS port where OpenSearch/Elasticsearch serves its API
_OPENSEARCH_PORT: int = 9200

# Required keyUsage bit fields
_REQUIRED_KEY_USAGES: list[str] = [
    "digital signature",
    "key encipherment",
]

# Required extendedKeyUsage values
_REQUIRED_EXTENDED_USAGES: list[str] = [
    "tls web server authentication",
]


class OpensearchCertKeyUsage(BaseTarget):
    """Checks TLS certificate key usage extensions on OpenSearch.

    Connects to the OpenSearch port via openssl and inspects the keyUsage
    and extendedKeyUsage X.509 extensions. Returns True only when all
    required key usage fields are present.
    """

    # Uses SSH to admin host for openssl cert inspection
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "OpenSearch TLS certificate key usage extensions"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Certs without digitalSignature + keyEncipherment in keyUsage and serverAuth "
            "in extendedKeyUsage are rejected by Java's TLS stack in OpenSearch plugins, "
            "causing «Remote end closed connection» errors (WPB-18068)."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Inspect the OpenSearch TLS certificate's key usage extensions.

        Returns:
            True if all required key usage extensions are present, False otherwise.

        Raises:
            RuntimeError: If the OpenSearch certificate cannot be retrieved.
        """
        es_host: str = self.config.databases.elasticsearch
        self.terminal.step(
            f"Checking OpenSearch TLS cert key usage on {es_host}:{_OPENSEARCH_PORT}..."
        )

        # < /dev/null is more reliable than «echo Q |» for closing openssl stdin:
        # signals EOF immediately so s_client exits cleanly after TLS handshake
        # without needing a quit byte. 2>&1 is intentional s_client writes
        # handshake diagnostics to stderr; merging lets us detect «no peer certificate»
        # or connection errors.
        cmd: str = (
            f"openssl s_client "
            f"-connect {es_host}:{_OPENSEARCH_PORT} "
            f"-servername {es_host} "
            f"< /dev/null 2>&1 "
            f"| openssl x509 -noout -text 2>/dev/null"
        )

        result = self.run_ssh(self.config.admin_host.ip, cmd)
        output: str = result.stdout.strip()

        # «no peer certificate available» appears in merged stderr when openssl
        # connects but server presents no cert (TLS not configured)
        if not output or "no peer certificate" in output.lower() or "unable to load certificate" in output.lower():
            # Capture diagnostic snippet from combined output to aid debugging
            diag: str = output[:300] if output else result.stderr.strip()[:300]
            raise RuntimeError(
                f"Could not retrieve TLS certificate from "
                f"{es_host}:{_OPENSEARCH_PORT}"
                + (f": {diag}" if diag else "")
            )

        output_lower: str = output.lower()

        # Check for required keyUsage bit fields
        missing_key_usages: list[str] = [
            ku for ku in _REQUIRED_KEY_USAGES if ku not in output_lower
        ]

        # Check for required extendedKeyUsage values
        missing_ext_usages: list[str] = [
            eku for eku in _REQUIRED_EXTENDED_USAGES if eku not in output_lower
        ]

        all_present: bool = (
            len(missing_key_usages) == 0 and len(missing_ext_usages) == 0
        )

        if all_present:
            self._health_info = (
                "OpenSearch certificate has correct keyUsage (digitalSignature, "
                "keyEncipherment) and extendedKeyUsage (serverAuth)"
            )
        else:
            missing_all: list[str] = missing_key_usages + missing_ext_usages
            self._health_info = (
                f"OpenSearch certificate missing key usage extension(s): "
                f"{', '.join(missing_all)}. Regenerate with correct key usage."
            )

        return all_present
