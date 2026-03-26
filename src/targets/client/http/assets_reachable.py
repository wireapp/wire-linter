"""Tests if Wire assets endpoint is reachable from a client network.

Part of --source client mode. The assets endpoint (assets.<domain>) serves
user-uploaded files: images, voice messages, file attachments.
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


class ClientAssetsReachable(BaseTarget):
    """Test if the Wire assets endpoint is reachable via HTTPS.

    Only runs in client mode (--source client). Uses HEAD since we don't
    want to download an actual asset.
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Wire assets endpoint reachability from client network"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The assets endpoint (assets.<domain>) serves images, files, and voice "
            "messages. If unreachable, users can't view images, download files, or "
            "listen to voice messages."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test HTTPS HEAD to the assets URL.

        Returns:
            JSON string with reachability details.
        """
        domain: str = self.config.cluster.domain
        url: str = f"https://assets.{domain}/"

        self.terminal.step(f"Testing assets reachability: {url}")

        reachable: bool = False
        status_code: int = 0
        response_time_ms: int = 0
        error_msg: str = ""

        try:
            ctx = ssl.create_default_context()
            start: float = time.monotonic()
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Wire-Fact-Gathering-Tool/1.0")

            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                status_code = resp.status
                response_time_ms = int((time.monotonic() - start) * 1000)
                reachable = True

        except urllib.error.HTTPError as e:
            status_code = e.code
            # Even 403/404 means the server is reachable
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
            self._health_info = f"Assets endpoint reachable: {url} (HTTP {status_code})"
        else:
            self._health_info = f"Assets endpoint NOT reachable: {url} — {error_msg}"

        return json.dumps(result)
