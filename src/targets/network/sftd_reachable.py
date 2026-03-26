"""Checks if SFTd (conference calling) HTTPS endpoint is reachable.

Group calls with 3+ people don't work without SFTd, so we check that
sftd.<domain> resolves and responds to HTTPS.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.http_client import HttpResult


class SftdReachable(BaseTarget):
    """Checks if SFTd is reachable via HTTPS from the internet.

    Hits the HTTPS endpoint directly from here to see if the conference
    calling service is actually accessible.
    """

    # This needs to run from the internet, not from the admin host
    # (otherwise we're just testing internal network access, not actual reachability).
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """What we're checking."""
        return "SFTd (conference calling) HTTPS reachable"

    @property
    def explanation(self) -> str:
        """Why we care and what healthy looks like."""
        return (
            "Without SFTd, group calls with 3+ people don't work. "
            "We're good if sftd.<domain> responds with anything under HTTP 500."
        )

    @property
    def unit(self) -> str:
        """No unit this is just a yes/no check."""
        return ""

    def collect(self) -> bool:
        """Try hitting the SFTd HTTPS endpoint.

        Needs this machine to have internet access (when requires_external_access
        is True), then returns True if we get a response, False if we don't.
        """
        domain: str = self.config.cluster.domain
        url: str = f"https://sftd.{domain}/"

        self.terminal.step(f"Checking SFTd at {url}...")

        # Make the request directly from here (not via SSH to the admin host)
        # so we actually see what external clients would see.
        result: HttpResult = self.http_get(url)

        if result.status_code == 0:
            self._health_info = f"Could not reach SFTd: {result.error}"
            return False

        code: int = result.status_code

        # Any response (even 404) means the server is running
        reachable: bool = code > 0 and code < 500

        if reachable:
            self._health_info = f"SFTd responding (HTTP {code})"
        else:
            self._health_info = f"SFTd not reachable (HTTP {code})"

        return reachable
