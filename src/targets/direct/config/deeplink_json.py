"""Checks deeplink.json has all required keys via direct HTTP.

Mobile clients refuse to connect if any key is missing. Required:
backendURL, backendWSURL, teamsURL, accountsURL, blackListURL, websiteURL, title.

This is the direct-HTTP variant of src/targets/config/deeplink_json.py
for use when the linter can reach the Wire domain without SSH tunneling.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget
from src.lib.http_client import HttpResult


# Keys that must be present in deeplink.json for mobile clients
_REQUIRED_KEYS: list[str] = [
    "backendURL",
    "backendWSURL",
    "teamsURL",
    "accountsURL",
    "blackListURL",
    "websiteURL",
    "title",
]


class DeeplinkJson(BaseTarget):
    """Checks deeplink.json completeness via direct HTTP.

    Fetches from the nginz-https endpoint directly from the linter machine
    (no SSH needed) and verifies all required keys are present.
    """

    # Direct HTTP to the Wire domain — only works from outside the cluster
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """What this target checks."""
        return "deeplink.json completeness for mobile clients (direct HTTP)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Mobile clients refuse to connect if any required key is missing. "
            "Healthy when all keys present."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Fetch and validate deeplink.json via direct HTTP.

        Returns:
            True if all required keys are present, False otherwise.

        Raises:
            RuntimeError: If deeplink.json can't be fetched or parsed.
        """
        domain: str = self.config.cluster.domain
        url: str = f"https://nginz-https.{domain}/deeplink.json"

        self.terminal.step(f"Fetching {url}...")

        result: HttpResult = self.http_get(url, timeout=10)

        # Handle connection failures (DNS resolution, network unreachable, etc.)
        if result.error:
            raise RuntimeError(
                f"Can't fetch deeplink.json from {url}: {result.error}"
            )

        # Handle non-success HTTP status codes
        if not result.success:
            raise RuntimeError(
                f"deeplink.json fetch returned HTTP {result.status_code}: "
                f"{result.body[:200]}"
            )

        body: str = result.body.strip()

        if not body:
            raise RuntimeError(
                f"Can't fetch deeplink.json from {url} "
                f"(HTTP {result.status_code}, empty body)"
            )

        try:
            deeplink: dict = json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(f"deeplink.json is not valid JSON: {body[:200]}")

        # Keys may be nested under "endpoints" or "custom"
        data_to_check: dict = deeplink

        if "endpoints" in deeplink:
            data_to_check = deeplink["endpoints"]
        elif "custom" in deeplink:
            data_to_check = deeplink.get("custom", {})

        present: list[str] = []
        missing: list[str] = []

        for key in _REQUIRED_KEYS:
            if key in data_to_check:
                present.append(key)
            else:
                missing.append(key)

        all_present: bool = len(missing) == 0

        if all_present:
            self._health_info = f"All {len(_REQUIRED_KEYS)} required keys present"
        else:
            self._health_info = f"Missing keys: {', '.join(missing)}"

        return all_present
