"""Tests TLS certificate validity for all Wire subdomains from a client network.

Part of --source client mode. Connects via TLS to each subdomain and checks:
certificate expiry, chain completeness, and subject/SAN match.
"""

from __future__ import annotations

# External
import json
import socket
import ssl
from datetime import datetime, timezone
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, SourceMode


class ClientCertificateValidity(BaseTarget):
    """Check TLS certificates for all Wire subdomains.

    Only runs in client mode (--source client).
    """

    # Only runs in client mode
    source_mode: SourceMode = SourceMode.CLIENT

    @property
    def description(self) -> str:
        """What this target checks."""
        return "TLS certificate validity for Wire subdomains"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire clients connect via TLS to all backend services. If certificates "
            "are expired, have incomplete chains, or don't match the domain, clients "
            "will reject the connection — often with cryptic error messages."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check TLS certificates for all Wire subdomains.

        Returns:
            JSON string with per-subdomain certificate details.
        """
        domain: str = self.config.cluster.domain
        self.terminal.step(f"Checking TLS certificates for {domain} subdomains...")

        # Subdomains to check (same list as DNS resolution target)
        subdomains: list[str] = [
            f"nginz-https.{domain}",
            f"nginz-ssl.{domain}",
            f"webapp.{domain}",
            f"assets.{domain}",
            f"account.{domain}",
        ]

        if self.config.options.expect_calling and self.config.options.expect_sft:
            subdomains.append(f"sftd.{domain}")

        results: list[dict[str, Any]] = []

        for subdomain in subdomains:
            self.terminal.step(f"  Checking TLS for {subdomain}...")
            cert_info: dict[str, Any] = self._check_cert(subdomain)
            results.append(cert_info)

        valid_count: int = sum(1 for r in results if r["valid"])
        total_count: int = len(results)

        output: dict[str, Any] = {
            "results": results,
            "valid_count": valid_count,
            "total_count": total_count,
            "all_valid": valid_count == total_count,
        }

        if valid_count == total_count:
            self._health_info = f"All {total_count} TLS certificates valid"
        else:
            failed: list[str] = [r["subdomain"] for r in results if not r["valid"]]
            self._health_info = f"{valid_count}/{total_count} valid. Issues: {', '.join(failed)}"

        return json.dumps(output)

    def _check_cert(self, hostname: str) -> dict[str, Any]:
        """Check a single hostname's TLS certificate.

        Args:
            hostname: The hostname to connect to and verify.

        Returns:
            Dict with certificate validity details.
        """
        result: dict[str, Any] = {
            "subdomain": hostname,
            "valid": False,
            "expiry": "",
            "days_remaining": -1,
            "issuer": "",
            "error": "",
        }

        try:
            # Use default CA bundle for chain validation
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert: dict[str, Any] = ssock.getpeercert()

                    # Parse expiry
                    not_after_str: str = cert.get("notAfter", "")
                    if not_after_str:
                        # OpenSSL date format: "Mar 25 12:00:00 2027 GMT"
                        not_after: datetime = datetime.strptime(
                            not_after_str, "%b %d %H:%M:%S %Y %Z"
                        ).replace(tzinfo=timezone.utc)
                        now: datetime = datetime.now(timezone.utc)
                        days_remaining: int = (not_after - now).days

                        result["expiry"] = not_after.isoformat()
                        result["days_remaining"] = days_remaining

                    # Parse issuer
                    issuer_tuples: tuple[Any, ...] = cert.get("issuer", ())
                    for item in issuer_tuples:
                        for kv in item:
                            if kv[0] == "organizationName":
                                result["issuer"] = str(kv[1])

                    result["valid"] = True

        except ssl.SSLCertVerificationError as e:
            result["error"] = f"Certificate verification failed: {e}"
        except ssl.SSLError as e:
            result["error"] = f"SSL error: {e}"
        except (socket.timeout, socket.gaierror, OSError) as e:
            result["error"] = f"Connection failed: {e}"

        return result
