"""Tests if the SFT (conference calling) signaling endpoint is reachable from a client network.

Part of --source client mode. SFT uses HTTPS for call setup/signaling.
If the SFT endpoint isn't reachable, clients can't create or join conference calls.
"""

from __future__ import annotations

# External
import json
import ssl
import time
import urllib.request
import urllib.error

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class ClientSftReachable(BaseTarget):
    """Test if the SFT signaling endpoint is reachable via HTTPS.

    Only runs in client mode (--source client) when calling and SFT are enabled.
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "SFT conference calling endpoint reachability"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The SFT (Selective Forwarding TURN) service handles conference call "
            "signaling via HTTPS. If sftd.<domain> isn't reachable, clients can't "
            "create or join group calls."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test HTTPS GET to the SFT endpoint.

        Returns:
            JSON string with reachability details.

        Raises:
            NotApplicableError: If calling or SFT is not enabled.
        """
        if not self.config.options.expect_calling:
            raise NotApplicableError("Calling is not enabled")
        if not self.config.options.expect_sft:
            raise NotApplicableError("SFT (conference calling) is not enabled")

        domain: str = self.config.cluster.domain
        url: str = f"https://sftd.{domain}/"

        self.terminal.step(f"Testing SFT reachability: {url}")

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
                reachable = True

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
            self._health_info = f"SFT reachable: {url} (HTTP {status_code})"
        else:
            self._health_info = f"SFT NOT reachable: {url} — {error_msg}"

        return json.dumps(result)
