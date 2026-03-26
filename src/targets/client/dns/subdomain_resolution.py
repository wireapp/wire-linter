"""Tests DNS resolution of all expected Wire subdomains from a client network.

Part of --source client mode. Resolves all Wire subdomains (webapp, nginz-https,
nginz-ssl, assets, account, teams, sftd, federator) from wherever the runner
is executing to verify that a Wire client on this network can find the backend.
"""

from __future__ import annotations

# External
import json
import socket
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, SourceMode


class ClientSubdomainResolution(BaseTarget):
    """Resolve all Wire subdomains from a client network vantage point.

    Only runs in client mode (--source client).
    """

    # Only runs in client mode
    source_mode: SourceMode = SourceMode.CLIENT

    @property
    def description(self) -> str:
        """What this target checks."""
        return "DNS resolution of Wire subdomains from client network"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire clients need to resolve several subdomains to use the backend: "
            "webapp, API (nginz-https), websocket (nginz-ssl), assets, account pages, "
            "and optionally team settings, SFT, and federator. If any don't resolve, "
            "clients on this network can't reach that service."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Resolve all expected Wire subdomains.

        Returns:
            JSON string with per-subdomain resolution results.
        """
        domain: str = self.config.cluster.domain
        self.terminal.step(f"Resolving Wire subdomains for {domain}...")

        # Build the list of subdomains to check
        subdomains: list[str] = [
            f"nginz-https.{domain}",
            f"nginz-ssl.{domain}",
            f"webapp.{domain}",
            f"assets.{domain}",
            f"account.{domain}",
            f"teams.{domain}",
        ]

        # Conditionally add calling/federation subdomains
        if self.config.options.expect_calling and self.config.options.expect_sft:
            subdomains.append(f"sftd.{domain}")

        if self.config.options.expect_federation:
            subdomains.append(f"federator.{domain}")

        results: list[dict[str, Any]] = []

        for subdomain in subdomains:
            self.terminal.step(f"  Resolving {subdomain}...")
            resolved: bool = False
            ip: str = ""
            error_msg: str = ""

            try:
                addr_info = socket.getaddrinfo(subdomain, 443, socket.AF_INET, socket.SOCK_STREAM)
                if addr_info:
                    # First result, fourth tuple element is (ip, port)
                    ip = addr_info[0][4][0]
                    resolved = True
            except socket.gaierror as e:
                error_msg = str(e)
            except OSError as e:
                error_msg = str(e)

            results.append({
                "subdomain": subdomain,
                "resolved": resolved,
                "ip": ip,
                "error": error_msg,
            })

        resolved_count: int = sum(1 for r in results if r["resolved"])
        total_count: int = len(results)

        output: dict[str, Any] = {
            "results": results,
            "resolved_count": resolved_count,
            "total_count": total_count,
            "all_resolved": resolved_count == total_count,
        }

        if resolved_count == total_count:
            self._health_info = f"All {total_count} subdomains resolved"
        else:
            failed: list[str] = [r["subdomain"] for r in results if not r["resolved"]]
            self._health_info = f"{resolved_count}/{total_count} resolved. Failed: {', '.join(failed)}"

        return json.dumps(output)
