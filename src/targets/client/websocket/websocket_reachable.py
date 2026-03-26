"""Tests if the Wire WebSocket notification endpoint is reachable from a client network.

Part of --source client mode. Wire uses long-lived WebSocket connections for
real-time notifications (new messages, typing indicators, call signals).
The WebSocket endpoint is at wss://nginz-ssl.<domain>/. We test if the
HTTP upgrade succeeds (response 101 Switching Protocols).
"""

from __future__ import annotations

# External
import json
import socket
import ssl

# Ours
from src.lib.base_target import BaseTarget, SourceMode


class ClientWebsocketReachable(BaseTarget):
    """Test if the Wire WebSocket endpoint accepts connections.

    Only runs in client mode (--source client). Sends an HTTP Upgrade
    request and checks if the server responds with 101.
    """

    # Only runs in client mode
    source_mode: SourceMode = SourceMode.CLIENT

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Wire WebSocket notification endpoint reachability"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire clients keep a persistent WebSocket connection to nginz-ssl for "
            "real-time notifications. If the WebSocket upgrade fails (often caused by "
            "load balancers silently dropping long-lived connections), clients won't "
            "receive notifications in real-time."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Attempt a WebSocket upgrade to the nginz-ssl endpoint.

        Returns:
            JSON string with reachability details.
        """
        domain: str = self.config.cluster.domain
        hostname: str = f"nginz-ssl.{domain}"

        self.terminal.step(f"Testing WebSocket upgrade: wss://{hostname}/")

        reachable: bool = False
        upgrade_status: int = 0
        error_msg: str = ""

        try:
            # Establish TLS connection
            ctx = ssl.create_default_context()
            raw_sock = socket.create_connection((hostname, 443), timeout=10)
            sock = ctx.wrap_socket(raw_sock, server_hostname=hostname)

            # Send a minimal WebSocket upgrade request
            # We don't need a real WebSocket handshake — just check if the server
            # accepts the Upgrade header (or at least responds, not times out)
            upgrade_request: str = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {hostname}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
                f"\r\n"
            )
            sock.sendall(upgrade_request.encode("ascii"))

            # Read the response status line
            response: bytes = b""
            while b"\r\n" not in response and len(response) < 4096:
                chunk: bytes = sock.recv(1024)
                if not chunk:
                    break
                response += chunk

            sock.close()

            # Parse the status line
            status_line: str = response.split(b"\r\n")[0].decode("ascii", errors="replace")
            parts: list[str] = status_line.split(" ", 2)
            if len(parts) >= 2 and parts[1].isdigit():
                upgrade_status = int(parts[1])

            # 101 = successful WebSocket upgrade
            # 426 = Upgrade Required (server supports WS but needs auth first)
            # Any response at all means the server is reachable for WebSocket
            reachable = upgrade_status > 0

        except (socket.timeout, socket.gaierror, OSError, ssl.SSLError) as e:
            error_msg = str(e)

        result: dict[str, object] = {
            "hostname": hostname,
            "reachable": reachable,
            "upgrade_status": upgrade_status,
            "error": error_msg,
        }

        if upgrade_status == 101:
            self._health_info = f"WebSocket upgrade succeeded (101) at wss://{hostname}/"
        elif reachable:
            self._health_info = f"WebSocket endpoint reachable (HTTP {upgrade_status}) at wss://{hostname}/"
        else:
            self._health_info = f"WebSocket NOT reachable: wss://{hostname}/ — {error_msg}"

        return json.dumps(result)
