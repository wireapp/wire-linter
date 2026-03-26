"""Tests if the Wire API (nginz) is reachable from a client network.

Part of --source client mode. Performs an HTTPS GET to the nginz /status
endpoint. This is the main REST API entry point for all Wire client operations.
"""

from __future__ import annotations

# External
import json
import ssl
import time
import urllib.request
import urllib.error

# Ours
from src.lib.base_target import BaseTarget


class ClientApiReachable(BaseTarget):
    """Test if the Wire API (nginz-https) is reachable via HTTPS.

    Only runs in client mode (--source client).
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Wire API (nginz) reachability from client network"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The nginz-https endpoint is the main REST API for all Wire client "
            "operations. If it's not reachable, no Wire client can function — "
            "no login, no messages, no calls."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test HTTPS GET to the nginz /status endpoint.

        Returns:
            JSON string with reachability details.
        """
        domain: str = self.config.cluster.domain
        url: str = f"https://nginz-https.{domain}/status"

        self.terminal.step(f"Testing API reachability: {url}")

        reachable: bool = False
        status_code: int = 0
        response_time_ms: int = 0
        error_msg: str = ""

        try:
            ctx = ssl.create_default_context()

            start: float = time.monotonic()
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Wire-Fact-Gathering-Tool/1.0")

            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                status_code = resp.status
                response_time_ms = int((time.monotonic() - start) * 1000)
                reachable = 200 <= status_code < 400

        except urllib.error.HTTPError as e:
            status_code = e.code
            reachable = True
            error_msg = f"HTTP {e.code}: {e.reason}"

        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            error_msg = str(e)

        result: dict[str, object] = {
            "url": url,
            "reachable": reachable,
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "error": error_msg,
        }

        if reachable:
            self._health_info = f"API reachable: {url} (HTTP {status_code}, {response_time_ms}ms)"
        else:
            self._health_info = f"API NOT reachable: {url} — {error_msg}"

        return json.dumps(result)
