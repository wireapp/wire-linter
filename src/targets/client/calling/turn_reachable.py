"""Tests TURN/STUN server reachability from a client network.

Part of --source client mode. Tries to reach TURN servers via UDP (preferred
for call quality) and TCP (fallback). TURN/UDP being blocked by corporate
firewalls is one of the most common client calling issues.

TURN servers are discovered by resolving restund01.<domain> and restund02.<domain>.
"""

from __future__ import annotations

# External
import json
import socket
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class ClientTurnReachable(BaseTarget):
    """Test TURN server reachability from client network via UDP and TCP.

    Only runs in client mode (--source client) when calling is enabled.
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "TURN/STUN server reachability from client network"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "TURN servers (coturn) handle 1:1 call relay when direct peer-to-peer "
            "is not possible. They listen on port 3478 (UDP and TCP). If UDP is "
            "blocked (common in corporate firewalls), calls use TCP fallback "
            "(reduced quality). If both are blocked, calls only work peer-to-peer."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test TURN server reachability via UDP and TCP.

        Returns:
            JSON string with per-server reachability results.

        Raises:
            NotApplicableError: If calling is not enabled.
        """
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled in the deployment configuration")

        domain: str = self.config.cluster.domain
        self.terminal.step(f"Testing TURN server reachability for {domain}...")

        # Try to discover TURN servers by DNS (standard Wire naming)
        turn_hosts: list[str] = []
        for prefix in ["restund01", "restund02"]:
            hostname: str = f"{prefix}.{domain}"
            try:
                socket.getaddrinfo(hostname, 3478, socket.AF_INET, socket.SOCK_STREAM)
                turn_hosts.append(hostname)
            except (socket.gaierror, OSError):
                pass

        if not turn_hosts:
            # No TURN servers found via DNS — can't test
            self._health_info = "No TURN servers found via DNS (restund01/restund02)"
            result: dict[str, Any] = {
                "results": [],
                "turn_hosts_found": 0,
                "any_udp_reachable": False,
                "any_tcp_reachable": False,
            }
            return json.dumps(result)

        results: list[dict[str, Any]] = []

        for host in turn_hosts:
            self.terminal.step(f"  Testing {host}:3478 (UDP + TCP)...")

            # Test TCP reachability
            tcp_ok: bool = False
            try:
                with socket.create_connection((host, 3478), timeout=5):
                    tcp_ok = True
            except (socket.timeout, OSError):
                pass

            # Test UDP reachability (send a STUN binding request and see if we get a response)
            udp_ok: bool = False
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                # STUN binding request (minimal valid packet)
                # Type: 0x0001 (Binding Request), Length: 0, Magic Cookie, Transaction ID
                stun_request: bytes = (
                    b'\x00\x01'         # type: binding request
                    b'\x00\x00'         # length: 0
                    b'\x21\x12\xa4\x42' # magic cookie
                    b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b'  # transaction ID
                )
                addr_info = socket.getaddrinfo(host, 3478, socket.AF_INET, socket.SOCK_DGRAM)
                if addr_info:
                    target_ip: str = addr_info[0][4][0]
                    sock.sendto(stun_request, (target_ip, 3478))
                    # If we get any response, UDP works
                    sock.recvfrom(1024)
                    udp_ok = True
            except (socket.timeout, OSError):
                pass
            finally:
                sock.close()

            results.append({
                "host": host,
                "port": 3478,
                "udp_reachable": udp_ok,
                "tcp_reachable": tcp_ok,
            })

        any_udp: bool = any(r["udp_reachable"] for r in results)
        any_tcp: bool = any(r["tcp_reachable"] for r in results)

        output: dict[str, Any] = {
            "results": results,
            "turn_hosts_found": len(turn_hosts),
            "any_udp_reachable": any_udp,
            "any_tcp_reachable": any_tcp,
        }

        if any_udp:
            self._health_info = "TURN reachable via UDP (best quality)"
        elif any_tcp:
            self._health_info = "TURN reachable via TCP only (reduced call quality)"
        else:
            self._health_info = "TURN NOT reachable via UDP or TCP"

        return json.dumps(output)
