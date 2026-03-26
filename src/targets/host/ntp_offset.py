"""Measures the NTP clock offset on the admin host.

This differs from ntp_synchronized.py by giving you the actual offset amount
in milliseconds, not just a yes/no. Above 50 ms and Cassandra quorum starts
failing. Above 200 ms and you get TLS validation errors (JCT-158, JCT-156).
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget


class NtpOffset(BaseTarget):
    """Measures the NTP clock offset on the admin host.

    Attempts «chronyc» first since it's more precise, then falls back to
    «ntpq» or «timedatectl». Returns the offset in milliseconds.
    """

    # Uses SSH to admin host for NTP measurements
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Admin host NTP clock offset"

    @property
    def explanation(self) -> str:
        """Why NTP offset matters for this cluster."""
        return (
            "Over 50 ms and Cassandra quorum fails. Over 200 ms and TLS breaks "
            "(JCT-158, JCT-156). You want it under 50 ms."
        )

    @property
    def unit(self) -> str:
        """Measurement unit."""
        return "ms"

    def collect(self) -> float:
        """Measure the NTP clock offset via available tools.

        Tries «chronyc», «ntpq», and «timedatectl» in order.

        Returns:
            Offset in milliseconds (always non-negative).

        Raises:
            RuntimeError: If none of the NTP tools are available.
        """
        self.terminal.step("Measuring NTP clock offset...")

        offset_ms: float | None = self._offset_via_chronyc()

        if offset_ms is None:
            offset_ms = self._offset_via_ntpq()

        if offset_ms is None:
            offset_ms = self._offset_via_timedatectl()

        if offset_ms is None:
            raise RuntimeError(
                "Could not measure NTP offset (chronyc, ntpq, and timedatectl all unavailable)"
            )

        if offset_ms < 50.0:
            self._health_info = f"Offset {offset_ms:.2f} ms (within acceptable range)"
        elif offset_ms < 200.0:
            self._health_info = f"Offset {offset_ms:.2f} ms (WARNING: Cassandra may be affected)"
        else:
            self._health_info = (
                f"Offset {offset_ms:.2f} ms (CRITICAL: TLS validation and Cassandra at risk)"
            )

        return round(offset_ms, 3)

    def _offset_via_chronyc(self) -> float | None:
        """Extract offset from «chronyc tracking» output.

        Returns:
            Offset in milliseconds, or None if «chronyc» isn't available.
        """
        result = self.run_ssh(self.config.admin_host.ip, "chronyc tracking")
        output: str = result.stdout.strip()

        if not output or "not running" in output.lower() or "cannot talk" in output.lower():
            return None

        for line in output.split("\n"):
            lower: str = line.lower()
            if "rms offset" in lower or "last offset" in lower:
                match = re.search(r":\s*([+-]?\d+\.\d+(?:e[+-]?\d+)?)\s*seconds", line, re.IGNORECASE)
                if match:
                    offset_seconds: float = abs(float(match.group(1)))
                    return offset_seconds * 1000.0

        return None

    def _offset_via_ntpq(self) -> float | None:
        """Extract offset from «ntpq -p» output.

        Returns:
            Offset in milliseconds, or None if «ntpq» isn't available.
        """
        result = self.run_ssh(self.config.admin_host.ip, "ntpq -p")
        output: str = result.stdout.strip()

        if not output or "connection refused" in output.lower():
            return None

        selected_offset: float | None = None
        candidate_offsets: list[float] = []
        # Collects every parsed offset regardless of peer status char,
        # so we can still return a value when all peers are in "reject" state
        all_offsets: list[float] = []

        for line in output.split("\n"):
            stripped: str = line.strip()

            # Skip blank lines, the header line ("remote  refid ..."), and
            # the separator line ("======...") before extracting any fields
            if not stripped or stripped.startswith("remote") or stripped.startswith("="):
                continue

            # First character is the NTP peer status marker (*, +, o, space, etc.)
            status_char: str = line[0]

            parts: list[str] = stripped.split()
            if len(parts) >= 9:
                try:
                    # ntpq columns: remote refid st t when poll reach delay offset jitter
                    # Non-space tally codes (*+o etc.) stay attached to remote after strip → 10 parts
                    # Space tally code loses its prefix after strip → 9 parts
                    # Offset is always the second-to-last field
                    offset_index: int = 8 if len(parts) >= 10 else 7
                    offset_val: float = abs(float(parts[offset_index]))
                    all_offsets.append(offset_val)
                    if status_char == "*":
                        selected_offset = offset_val
                    elif status_char in ("+", "o"):
                        candidate_offsets.append(offset_val)
                except (ValueError, IndexError):
                    continue

        if selected_offset is not None:
            return selected_offset

        if candidate_offsets:
            return min(candidate_offsets)

        # All peers may be in "reject" status (space prefix) during NTP startup;
        # return the smallest offset we found rather than falling through to None
        if all_offsets:
            return min(all_offsets)

        return None

    def _offset_via_timedatectl(self) -> float | None:
        """Extract offset from «timedatectl timesync-status» output.

        Falls back on systems running systemd-timesyncd without «chronyc»
        or «ntpq». Reports the last sync offset in forms like "+10.456ms",
        "+123us", or "+0.001234s".

        Returns:
            Offset in milliseconds, or None if unavailable or no offset reported.
        """
        result = self.run_ssh(self.config.admin_host.ip, "timedatectl timesync-status")
        output: str = result.stdout.strip()

        if not output or "unknown command" in output.lower() or "failed" in output.lower():
            return None

        for line in output.split("\n"):
            if "offset" not in line.lower():
                continue

            match = re.search(
                r"offset\s*:\s*([+-]?\d+(?:\.\d+)?)\s*(ms|us|µs|s)\b",
                line,
                re.IGNORECASE,
            )
            if not match:
                continue

            raw_value: float = abs(float(match.group(1)))
            unit: str = match.group(2).lower().replace("µ", "u")

            if unit == "ms":
                return raw_value
            elif unit == "us":
                return raw_value / 1000.0
            elif unit == "s":
                return raw_value * 1000.0

        return None
