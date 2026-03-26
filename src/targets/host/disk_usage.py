"""Checks root filesystem usage on the admin host.

Runs «df --output=pcent /» and parses the Use% column to find out how full the
root filesystem is. Returns the usage as an integer percentage. When this gets
high, logs or databases can fill the disk and break services.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class DiskUsage(BaseTarget):
    """Checks root filesystem usage on the admin host.

    The runner is the admin host, so we just call «df» locally and grab
    the Use% column as an integer.
    """

    @property
    def description(self) -> str:
        return "Root filesystem usage on admin host"

    @property
    def explanation(self) -> str:
        return (
            "A full root filesystem will block logging, Docker image pulls, and "
            "system updates. Above 90% is critical."
        )

    @property
    def unit(self) -> str:
        return "%"

    def collect(self) -> int:
        """Measure current root filesystem usage percentage.

        Returns:
            Integer percentage (0-100) of root filesystem used.

        Raises:
            RuntimeError: If df output cannot be parsed.
        """
        # Using --output=pcent avoids line-wrapping when paths are long
        # (LVM paths like /dev/mapper/ubuntu--vg-ubuntu--lv wrap with df -h)
        result = self.run_local(["df", "--output=pcent", "/"])

        # First line is the header, second is the actual percentage
        lines: list[str] = result.stdout.strip().split("\n")

        # Need both header and value to work with
        if len(lines) < 2:
            raise RuntimeError(
                f"Unexpected df output: expected header + data line, got {len(lines)} line(s)"
            )

        # Grab the second line and clean off whitespace and the % sign
        usage_str: str = lines[1].strip().rstrip("%")

        if not usage_str:
            raise RuntimeError("Unexpected df output: percentage line is empty")

        try:
            usage_pct: int = int(usage_str)
        except ValueError:
            raise RuntimeError(f"Could not parse disk usage percentage from df output: '{usage_str}'")

        # Summarize for the health report
        self._health_info = f"Admin host root filesystem {usage_pct}% used"

        return usage_pct
