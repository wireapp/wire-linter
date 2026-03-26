"""Tests TURN-over-TLS (TURNS) reachability from a client network.

Port 5349 is the TURN TLS port — a secure fallback when the standard
TURN ports (3478 UDP/TCP) are blocked.
"""

from __future__ import annotations

# External
import json
import socket
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class ClientTurnTlsReachable(BaseTarget):
    """Test TURNS (TURN over TLS, port 5349) reachability.

    Only runs in client mode when calling is enabled.
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "TURNS (TURN over TLS, port 5349) reachability"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "TURNS on port 5349 is a TLS-encrypted fallback for TURN traffic. "
            "When standard TURN ports (3478) are blocked, clients can use 5349. "
            "This port can be reconfigured to 443 to look like regular HTTPS traffic."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test TURNS reachability on port 5349.

        Returns:
            JSON string with reachability results.

        Raises:
            NotApplicableError: If calling is not enabled.
        """
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled")

        domain: str = self.config.cluster.domain
        self.terminal.step(f"Testing TURNS (port 5349) reachability for {domain}...")

        # Discover TURN servers by DNS
        turn_hosts: list[str] = []
        for prefix in ["restund01", "restund02"]:
            hostname: str = f"{prefix}.{domain}"
            try:
                socket.getaddrinfo(hostname, 5349, socket.AF_INET, socket.SOCK_STREAM)
                turn_hosts.append(hostname)
            except (socket.gaierror, OSError):
                pass

        results: list[dict[str, Any]] = []

        for host in turn_hosts:
            self.terminal.step(f"  Testing {host}:5349 (TLS)...")
            reachable: bool = False
            try:
                with socket.create_connection((host, 5349), timeout=5):
                    reachable = True
            except (socket.timeout, OSError):
                pass

            results.append({
                "host": host,
                "port": 5349,
                "reachable": reachable,
            })

        any_reachable: bool = any(r["reachable"] for r in results)

        output: dict[str, Any] = {
            "results": results,
            "turn_hosts_found": len(turn_hosts),
            "any_reachable": any_reachable,
        }

        if not turn_hosts:
            self._health_info = "No TURN servers found via DNS for TURNS check"
        elif any_reachable:
            self._health_info = "TURNS (port 5349) reachable"
        else:
            self._health_info = "TURNS (port 5349) NOT reachable"

        return json.dumps(output)
