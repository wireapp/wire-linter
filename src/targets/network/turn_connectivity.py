"""Checks TURN/Coturn UDP connectivity.

TURN failures mean voice and video calls silently break for users behind
restrictive firewalls. We test UDP connectivity to port 3478 on the Wire domain.
"""

from __future__ import annotations

import os
import struct

# Ours
from src.lib.base_target import BaseTarget

# STUN protocol constants (RFC 5389)
STUN_BINDING_REQUEST: int  = 0x0001
STUN_BINDING_RESPONSE: int = 0x0101
STUN_MAGIC_COOKIE: int     = 0x2112A442
STUN_HEADER_SIZE: int      = 20


def build_stun_binding_request() -> bytes:
    """Build a minimal 20-byte STUN Binding Request (RFC 5389).

    Format: 2B type | 2B length | 4B magic cookie | 12B transaction ID.
    No attributes, so message length is 0.

    Returns:
        20 bytes ready to send over UDP.
    """
    # 12 random bytes for the transaction ID
    transaction_id: bytes = os.urandom(12)

    # Pack header: type (0x0001), length (0), magic cookie, then append txn ID
    header: bytes = struct.pack(
        '!HHI', STUN_BINDING_REQUEST, 0, STUN_MAGIC_COOKIE,
    )
    return header + transaction_id


def is_stun_binding_response(data: bytes) -> bool:
    """Check whether raw bytes look like a valid STUN Binding Response.

    Validates the message type and magic cookie from the 20-byte STUN header.

    Args:
        data: Raw bytes received from the server.

    Returns:
        True if the response carries a STUN Binding Response header.
    """
    # Need at least a full STUN header
    if len(data) < STUN_HEADER_SIZE:
        return False

    # Unpack message type (first 2 bytes) and magic cookie (bytes 4-8)
    msg_type: int = struct.unpack('!H', data[0:2])[0]
    cookie: int   = struct.unpack('!I', data[4:8])[0]

    return msg_type == STUN_BINDING_RESPONSE and cookie == STUN_MAGIC_COOKIE


class TurnConnectivity(BaseTarget):
    """Checks TURN server UDP connectivity.

    Tests UDP and TCP to port 3478 directly from here to see if the relay
    is reachable from the internet.
    """

    # TURN reachability must be tested from the internet the admin host
    # is on the internal network and can't represent what external clients see.
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "TURN/Coturn UDP connectivity (port 3478)"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "TURN relays voice and video traffic for users behind restrictive firewalls. "
            "If it's unreachable, calls fail silently for those users. We check UDP 3478, "
            "TCP 3478, and whether the coturn pod is running."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement it's just yes/no, so empty."""
        return ""

    def collect(self) -> bool:
        """Test TURN server UDP connectivity.

        Run nc locally so we see what the internet sees, not what the admin
        network sees. Sends a real STUN Binding Request over UDP and validates
        the binary response (magic cookie + message type), avoiding fragile
        string-length checks on binary data.

        Returns:
            True if the TURN port responds, False otherwise.
        """
        domain: str = self.config.cluster.domain

        self.terminal.step(f"Testing TURN UDP connectivity to {domain}:3478...")

        # Build a STUN Binding Request to send as stdin to nc -u; this gives us
        # a real protocol probe instead of relying on exit-code heuristics alone.
        stun_request: bytes = build_stun_binding_request()

        # Send the STUN request over UDP and capture the raw binary response.
        # Domain is a plain argument so no shell metacharacter issues.
        result = self.run_local(
            ["nc", "-u", "-w", "3", domain, "3478"],
            stdin_data=stun_request,
        )

        # Try TCP as a fallback some TURN servers accept that too.
        # -z (zero-I/O scan mode) exits 0 on success, 1 on failure; domain is a
        # plain argument so no shell injection is possible.
        result_tcp = self.run_local(
            ["nc", "-z", "-w", "3", domain, "3478"],
        )

        # Exit code 0 means the TCP port accepted the connection.
        tcp_open: bool = result_tcp.exit_code == 0

        # Validate the raw STUN response bytes instead of checking decoded
        # string length; this correctly handles binary protocol data.
        udp_open: bool = result.exit_code == 0 and is_stun_binding_response(
            result.stdout_raw,
        )

        # Check if any coturn pods are running another sign things are working.
        cmd_result, pods_data = self.run_kubectl(
            "pods",
            selector="app=coturn",
        )

        coturn_running: bool = False
        if pods_data and pods_data.get("items"):
            for pod in pods_data["items"]:
                if pod.get("status", {}).get("phase") == "Running":
                    coturn_running = True
                    break

        # Combine the signals UDP is the main way TURN works, but TCP and running
        # pods are good signs too.
        reachable: bool = udp_open or tcp_open or coturn_running

        if udp_open and tcp_open and coturn_running:
            self._health_info = "TURN port 3478 open (UDP+TCP), coturn pod running"
        elif udp_open and coturn_running:
            self._health_info = "TURN port 3478 open (UDP), coturn pod running"
        elif tcp_open and coturn_running:
            self._health_info = "TURN port 3478 open (TCP only), coturn pod running"
        elif udp_open:
            self._health_info = "TURN port 3478 open (UDP)"
        elif tcp_open:
            self._health_info = "TURN port 3478 open (TCP only - UDP blocked)"
        elif coturn_running:
            self._health_info = "Coturn pod running but port 3478 not reachable externally"
        else:
            self._health_info = "TURN port 3478 not reachable, no coturn pod found"

        return reachable
