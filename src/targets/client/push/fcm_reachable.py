"""Tests Firebase Cloud Messaging (FCM) reachability from a client network.

Julia's documentation specifies: "As with APNs, this check should be performed
from the network where Android client devices will be operating."

FCM uses HTTPS on port 443 at fcm.googleapis.com.
"""

from __future__ import annotations

# External
import json
import ssl
import time
import urllib.request
import urllib.error

# Ours
from src.lib.base_target import BaseTarget, SourceMode


class ClientFcmReachable(BaseTarget):
    """Test FCM reachability from a client network.

    Only runs in client mode (--source client).
    """

    # Only runs in client mode
    source_mode: SourceMode = SourceMode.CLIENT

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Firebase Cloud Messaging (FCM) reachability"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Android devices use FCM (fcm.googleapis.com) for push notifications. "
            "Without FCM, Android clients can fall back to persistent WebSocket "
            "(battery drain), but FCM is the recommended method."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test FCM reachability on port 443.

        Returns:
            JSON string with reachability details.
        """
        self.terminal.step("Testing FCM reachability: fcm.googleapis.com...")

        reachable: bool = False
        error_msg: str = ""
        response_time_ms: int = 0
        status_code: int = 0

        try:
            ctx = ssl.create_default_context()
            start: float = time.monotonic()
            # Match Julia's documented check: curl -v --max-time 10 https://fcm.googleapis.com
            req = urllib.request.Request("https://fcm.googleapis.com", method="GET")
            req.add_header("User-Agent", "Wire-Fact-Gathering-Tool/1.0")
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                status_code = resp.status
                response_time_ms = int((time.monotonic() - start) * 1000)
                reachable = True
        except urllib.error.HTTPError as e:
            # Any HTTP response (even 4xx) confirms TCP+TLS connectivity
            status_code = e.code
            response_time_ms = int((time.monotonic() - start) * 1000)
            reachable = True
        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            error_msg = str(e)

        result: dict[str, object] = {
            "host": "fcm.googleapis.com",
            "reachable": reachable,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "error": error_msg,
        }

        if reachable:
            self._health_info = f"FCM reachable (HTTP {status_code}, {response_time_ms}ms)"
        else:
            self._health_info = f"FCM NOT reachable — {error_msg}"

        return json.dumps(result)
