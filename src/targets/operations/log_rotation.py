"""Checks that log rotation is configured with 72h max retention.

Wire's privacy promise says we delete logs after 72 hours.
This looks at the logrotate config on the admin host to see the max age setting.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class LogRotation(BaseTarget):
    """Checks log rotation configuration.

    Logs into the admin host and looks at the logrotate config
    to make sure retention settings are right.
    """

    # Uses SSH to admin host for logrotate config checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What we're checking shown to the user."""
        return "Log rotation configured (72h max retention)"

    @property
    def explanation(self) -> str:
        """Why we care about this check and what makes it pass or fail."""
        return (
            "Wire's privacy policy says old logs (over 72 hours) have to be deleted. "
            "If maxage is 3 days or less, we're good."
        )

    def collect(self) -> str:
        """Grab the logrotate config and check the retention settings.

        Returns:
            A short summary of what we found.
        """
        self.terminal.step("Checking log rotation configuration...")

        # Try to find the logrotate config could be for nginx, wire, or the main one
        result = self.run_ssh(
            self.config.admin_host.ip,
            "(cat /etc/logrotate.d/nginx 2>/dev/null"
            " || cat /etc/logrotate.d/wire* 2>/dev/null"
            " || cat /etc/logrotate.conf 2>/dev/null)"
            " | head -50",
        )

        output: str = result.stdout.strip()

        if not output:
            self._health_info = "No logrotate configuration found"
            return "not configured"

        # Check what rotation settings are in place
        has_maxage: bool = "maxage" in output.lower()
        has_rotate: bool = "rotate " in output.lower()
        has_daily: bool = "daily" in output.lower()

        # If maxage is set, pull out the actual value
        maxage_value: str = ""
        for line in output.split("\n"):
            if "maxage" in line.lower():
                parts: list[str] = line.strip().split()
                if len(parts) >= 2:
                    maxage_value = parts[1]

        if has_maxage and maxage_value:
            try:
                days: int = int(maxage_value)
                if days <= 3:
                    self._health_info = f"Log rotation: maxage {days} days (compliant with 72h policy)"
                    return f"maxage={days}d (compliant)"
                else:
                    self._health_info = f"WARNING: maxage {days} days exceeds 72h policy"
                    return f"maxage={days}d (exceeds 72h)"
            except ValueError:
                pass

        if has_daily and has_rotate:
            self._health_info = "Log rotation configured (daily with rotate)"
            return "daily rotation configured"

        self._health_info = f"Log rotation present but retention unclear"
        return "configured (check retention)"
