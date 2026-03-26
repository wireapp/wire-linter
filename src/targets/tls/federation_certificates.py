"""Checks federation TLS certificates in Kubernetes secrets.

Federation requires mutual TLS: the federator needs a client certificate
with the infrastructure domain as SAN, and CA certificates to verify partners.
"""

from __future__ import annotations

# External
import json
import base64
import subprocess
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class FederationCertificates(BaseTarget):
    """Check federation TLS certificates in Kubernetes secrets.

    Searches for federator TLS secrets and reports on certificate existence,
    expiry, and SANs. Only runs when federation is expected.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federation TLS certificates (client cert, CA certs)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federation uses mutual TLS for inter-backend authentication. The federator "
            "needs a client certificate (with the infrastructure domain as SAN) and CA "
            "certificates to verify federation partners. Expired or missing certificates "
            "break federation completely."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check federation TLS secrets.

        Returns:
            JSON string with certificate details.

        Raises:
            NotApplicableError: If federation is not expected.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")

        self.terminal.step("Searching for federation TLS certificates...")

        _result, data = self.run_kubectl("secrets")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch secret list")

        items: list[dict[str, Any]] = data.get("items", [])

        client_cert_found: bool = False
        client_cert_expiry: str = ""
        client_cert_sans: list[str] = []
        client_cert_days_remaining: int = -1
        ca_certs_found: bool = False
        ca_cert_count: int = 0

        for secret in items:
            name: str = secret.get("metadata", {}).get("name", "")
            secret_type: str = secret.get("type", "")
            data_keys: list[str] = list(secret.get("data", {}).keys())

            # Look for federator TLS secrets
            is_fed_tls: bool = (
                "federator" in name.lower()
                and ("tls" in name.lower() or secret_type == "kubernetes.io/tls")
            )

            if is_fed_tls:
                # Check if it's a client cert or CA cert
                has_cert: bool = "tls.crt" in data_keys or "cert.pem" in data_keys
                has_ca: bool = "ca.crt" in data_keys or "ca.pem" in data_keys

                if has_cert:
                    client_cert_found = True
                    # Try to decode and parse the certificate
                    cert_key: str = "tls.crt" if "tls.crt" in data_keys else "cert.pem"
                    cert_b64: str = secret.get("data", {}).get(cert_key, "")
                    if cert_b64:
                        cert_info: dict[str, Any] = self._parse_cert_b64(cert_b64)
                        client_cert_expiry = cert_info.get("expiry", "")
                        client_cert_sans = cert_info.get("sans", [])
                        client_cert_days_remaining = cert_info.get("days_remaining", -1)

                if has_ca:
                    ca_certs_found = True
                    ca_cert_count += 1

            # Also check for federation ingress CA secrets
            if "federation" in name.lower() and ("ca" in name.lower() or "trust" in name.lower()):
                ca_certs_found = True
                ca_cert_count += 1

        result: dict[str, Any] = {
            "client_cert_found": client_cert_found,
            "client_cert_expiry": client_cert_expiry,
            "client_cert_sans": client_cert_sans,
            "client_cert_days_remaining": client_cert_days_remaining,
            "ca_certs_found": ca_certs_found,
            "ca_cert_count": ca_cert_count,
        }

        parts: list[str] = []
        if client_cert_found:
            parts.append(f"client cert: found (expires: {client_cert_expiry or 'unknown'})")
        else:
            parts.append("client cert: NOT FOUND")
        if ca_certs_found:
            parts.append(f"CA certs: {ca_cert_count}")
        else:
            parts.append("CA certs: NOT FOUND")

        self._health_info = ", ".join(parts)
        return json.dumps(result)

    def _parse_cert_b64(self, cert_b64: str) -> dict[str, Any]:
        """Parse a base64-encoded certificate and extract details.

        Args:
            cert_b64: Base64-encoded certificate data from Kubernetes secret.

        Returns:
            Dict with expiry, SANs, days_remaining.
        """
        result: dict[str, Any] = {"expiry": "", "sans": [], "days_remaining": -1}

        try:
            cert_pem: bytes = base64.b64decode(cert_b64)

            # Use openssl to parse the cert (stdlib ssl can't parse PEM directly)
            proc = subprocess.run(
                ["openssl", "x509", "-noout", "-enddate", "-subject", "-ext", "subjectAltName"],
                input=cert_pem,
                capture_output=True,
                timeout=10,
            )

            output: str = proc.stdout.decode("utf-8", errors="replace")

            # Parse expiry
            for line in output.split("\n"):
                if "notAfter=" in line:
                    date_str: str = line.split("=", 1)[1].strip()
                    result["expiry"] = date_str

                # Parse SANs
                if "DNS:" in line:
                    sans: list[str] = []
                    for part in line.split(","):
                        part = part.strip()
                        if part.startswith("DNS:"):
                            sans.append(part[4:])
                    result["sans"] = sans

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return result
