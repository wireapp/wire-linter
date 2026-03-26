"""Tests if the deeplink.json is available and valid from a client network.

Part of --source client mode. The deeplink.json helps mobile clients
auto-discover backend settings (API URL, WebSocket URL, team settings URL).
"""

from __future__ import annotations

# External
import json
import ssl
import urllib.request
import urllib.error
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class ClientDeeplinkJson(BaseTarget):
    """Test if deeplink.json is reachable and valid from a client network.

    Only runs in client mode when deeplink is expected.
    """

    # Only runs in client mode
    client_mode_only: bool = True
    backend_mode_only: bool = False

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Deeplink.json availability and validity"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The deeplink.json file helps mobile Wire clients auto-discover backend "
            "settings. Without it, users must manually configure their clients."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Fetch and validate deeplink.json.

        Returns:
            JSON string with reachability and validity details.

        Raises:
            NotApplicableError: If deeplink is not expected.
        """
        if not self.config.options.expect_deeplink:
            raise NotApplicableError("Deeplink is not enabled in the deployment configuration")

        domain: str = self.config.cluster.domain
        url: str = f"https://nginz-https.{domain}/.well-known/deeplink.json"

        self.terminal.step(f"Fetching deeplink.json: {url}")

        reachable: bool = False
        valid_json: bool = False
        fields: dict[str, Any] = {}
        error_msg: str = ""

        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Wire-Fact-Gathering-Tool/1.0")

            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                reachable = True
                body: str = resp.read().decode("utf-8", errors="replace")

                try:
                    parsed: Any = json.loads(body)
                    if isinstance(parsed, dict):
                        valid_json = True
                        # Extract key fields
                        for key in ["backendURL", "backendWSURL", "teamsURL", "accountsURL", "title"]:
                            if key in parsed:
                                fields[key] = str(parsed[key])
                except json.JSONDecodeError:
                    error_msg = "Response is not valid JSON"

        except urllib.error.HTTPError as e:
            reachable = True
            error_msg = f"HTTP {e.code}: {e.reason}"

        except (urllib.error.URLError, OSError, ssl.SSLError) as e:
            error_msg = str(e)

        result: dict[str, Any] = {
            "url": url,
            "reachable": reachable,
            "valid_json": valid_json,
            "fields": fields,
            "error": error_msg,
        }

        if valid_json:
            self._health_info = f"Deeplink.json valid: {len(fields)} field(s)"
        elif reachable:
            self._health_info = f"Deeplink.json reachable but invalid: {error_msg}"
        else:
            self._health_info = f"Deeplink.json NOT reachable: {error_msg}"

        return json.dumps(result)
