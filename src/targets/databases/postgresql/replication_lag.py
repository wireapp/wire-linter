"""Checks PostgreSQL replication lag between primary and standbys.

When the lag gets high, standbys fall behind with stale data, and you'd lose
recent writes if there's a failover. Queries pg_stat_replication on the primary.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget


class PostgresqlReplicationLag(BaseTarget):
    """Checks PostgreSQL replication lag.

    Connects to the PostgreSQL host via SSH and queries
    pg_stat_replication for replay_lag values.
    """

    # Uses SSH to reach PostgreSQL nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "PostgreSQL replication lag"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "When standbys fall behind, you've got stale data and a failover'd lose writes. "
            "You want replay_lag to be zero or close to it."
        )

    def collect(self) -> str:
        """Query pg_stat_replication for replication lag.

        Returns:
            Replication lag summary string.

        Raises:
            RuntimeError: If the query fails or returns no data.
        """
        self.terminal.step("Checking PostgreSQL replication lag...")

        # Grab replay_lag from pg_stat_replication on the primary
        result = self.run_db_command(
            self.config.databases.postgresql,
            "sudo -u postgres psql -t -c"
            " \"SELECT application_name, replay_lag, state"
            " FROM pg_stat_replication\" 2>/dev/null",
        )

        output: str = result.stdout.strip()

        # Empty output could mean this is a standby, not the primary
        if not output or output == "(0 rows)":
            # Try checking if we're on a standby instead
            standby_check = self.run_db_command(
                self.config.databases.postgresql,
                "sudo -u postgres psql -t -c 'SELECT pg_is_in_recovery()' 2>/dev/null",
            )

            if standby_check.stdout.strip() == "t":
                self._health_info = "This node is a standby (not the primary)"
                return "standby (no replication data)"

            self._health_info = "No replication slots found (standalone or primary without standbys)"
            return "no replication"

        # Parse each line from the output (one row per standby)
        entries: list[str] = []
        max_lag_seconds: float = 0.0

        for line in output.split("\n"):
            if not line.strip() or "row" in line.lower():
                continue

            parts: list[str] = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                app_name: str = parts[0] or "unknown"
                raw_lag: str = parts[1].strip()
                state: str = parts[2] if len(parts) > 2 else "?"

                # NULL replay_lag means the standby's caught up
                lag: str = raw_lag if raw_lag else "0"
                entries.append(f"{app_name}: lag={lag}, state={state}")

                # Parse the lag interval to seconds for threshold comparison
                lag_seconds: float = self._parse_pg_interval_seconds(raw_lag)
                if lag_seconds > max_lag_seconds:
                    max_lag_seconds = lag_seconds

        summary: str = "; ".join(entries)

        # Streaming replication's gonna have some lag under a second, that's normal.
        # Only flag it if we're over a second.
        if max_lag_seconds > 1.0:
            self._health_info = f"Replication lag detected: {summary}"
        else:
            self._health_info = f"No significant lag: {summary}"

        return summary if summary else output[:200]

    @staticmethod
    def _parse_pg_interval_seconds(interval_str: str) -> float:
        """Parse a PostgreSQL interval string to total seconds.

        Postgres spits out intervals in various formats:
          "00:00:00"             (under 24 hours, no decimals)
          "00:00:00.003795"      (under 24 hours, with microseconds)
          "1 day 00:30:00"       (over 24 hours, singular)
          "2 days 01:00:00.5"    (over 24 hours, plural, fractional)

        Returns 0.0 for empty, null, or anything we can't parse.

        Args:
            interval_str: The PostgreSQL interval string.

        Returns:
            Total seconds as a float.
        """
        if not interval_str or interval_str == "?":
            return 0.0

        try:
            # Regex matches "N day(s) " prefix (optional) then HH:MM:SS[.frac].
            # We need this because float("1 day 00") bombs and we'd hide severe lag.
            pattern: str = r"^(?:(\d+)\s+days?\s+)?(\d+):(\d+):(\d+(?:\.\d+)?)$"
            match: re.Match[str] | None = re.match(pattern, interval_str.strip())
            if not match:
                return 0.0

            days: float = float(match.group(1)) if match.group(1) else 0.0
            hours: float = float(match.group(2))
            minutes: float = float(match.group(3))
            seconds: float = float(match.group(4))

            return days * 86400 + hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return 0.0
