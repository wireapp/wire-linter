"""Tests Apple Push Notification service (APNs) reachability from a client network.

Julia's documentation specifies: "This check must be performed from the client
device's network, not from your backend server. APNs connectivity is a requirement
of the mobile device, not the Wire backend."

APNs uses HTTPS on port 443 (HTTP/2) with a legacy fallback on port 2197.
"""

from __future__ import annotations

# External
import json
import socket
import ssl
import time
import urllib.request
import urllib.error

# Ours
from src.lib.base_target import BaseTarget


class ClientApnsReachable(BaseTarget):
    """Test APNs reachability from a client network.

    Only runs in client mode (--source client). Checks both the primary
    endpoint (port 443) and the legacy port (2197).
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Apple Push Notification service (APNs) reachability"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "iOS devices require connectivity to APNs (api.push.apple.com) to receive "
            "push notifications. Without APNs, iOS Wire clients only receive "
            "notifications when the app is actively open. There is no WebSocket "
            "fallback for iOS."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test APNs reachability on port 443 and legacy port 2197.

        Returns:
            JSON string with reachability details per port.
        """
        self.terminal.step("Testing APNs reachability: api.push.apple.com...")

        # Test primary endpoint (port 443, HTTP/2)
        port_443_ok: bool = False
        port_443_error: str = ""
        port_443_time_ms: int = 0

        self.terminal.step("  Port 443 (primary, HTTP/2)...")
        try:
            ctx = ssl.create_default_context()
            start: float = time.monotonic()
            req = urllib.request.Request("https://api.push.apple.com", method="GET")
            req.add_header("User-Agent", "Wire-Fact-Gathering-Tool/1.0")
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                port_443_ok = True
                port_443_time_ms = int((time.monotonic() - start) * 1000)
        except urllib.error.HTTPError:
            # Any HTTP response (even 4xx/5xx) confirms TCP+TLS connectivity
            port_443_ok = True
            port_443_time_ms = int((time.monotonic() - start) * 1000)
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            port_443_error = str(e)

        # Test legacy endpoint (port 2197)
        port_2197_ok: bool = False
        port_2197_error: str = ""

        self.terminal.step("  Port 2197 (legacy fallback)...")
        try:
            with socket.create_connection(("api.push.apple.com", 2197), timeout=10):
                port_2197_ok = True
        except (socket.timeout, OSError) as e:
            port_2197_error = str(e)

        any_reachable: bool = port_443_ok or port_2197_ok

        result: dict[str, object] = {
            "host": "api.push.apple.com",
            "port_443_reachable": port_443_ok,
            "port_443_error": port_443_error,
            "port_443_time_ms": port_443_time_ms,
            "port_2197_reachable": port_2197_ok,
            "port_2197_error": port_2197_error,
            "any_reachable": any_reachable,
        }

        if port_443_ok:
            self._health_info = f"APNs reachable on port 443 ({port_443_time_ms}ms)"
        elif port_2197_ok:
            self._health_info = "APNs reachable on legacy port 2197 only"
        else:
            self._health_info = f"APNs NOT reachable — {port_443_error}"

        return json.dumps(result)
