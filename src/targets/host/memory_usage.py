"""Checks memory usage on the admin host.

Runs «free -b» to get memory statistics in bytes, then computes usage
percentage from total and available memory. We update the description
with actual GiB figures so operators can see the real values without
doing math.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class MemoryUsage(BaseTarget):
    """Checks memory usage on the admin host.

    Runs «free -b» locally and computes (total available) / total as a
    percentage. We use «available» memory instead of «used» because it
    includes reclaimable cache, which gives a much better sense of actual
    memory pressure on the system.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Memory usage on admin host"

    @property
    def explanation(self) -> str:
        """Why this matters and when it's a problem."""
        return (
            "High memory usage causes OOM kills of Docker containers and system processes. "
            "We measure «available» memory to include reclaimable cache, which gives a "
            "better picture of memory pressure."
        )

    @property
    def unit(self) -> str:
        """Percentage."""
        return "%"

    def collect(self) -> int:
        """Measure current memory usage percentage on the admin host.

        Returns:
            Integer percentage (0-100) of memory in use.

        Raises:
            RuntimeError: If free output is missing the Mem: line, has unexpected format,
                or reports zero/negative total memory.
        """
        # Use -b to get raw bytes instead of KB/MB/GB which vary by locale
        result = self.run_local(["free", "-b"])

        # Find the Mem: line (its position varies if swap is present)
        lines: list[str] = result.stdout.strip().split("\n")

        mem_line: str = ""
        for line in lines:
            if line.startswith("Mem:"):
                mem_line = line
                break

        if not mem_line:
            raise RuntimeError("Could not find 'Mem:' line in free output")

        # Parse columns: label total used free shared buff/cache available
        fields: list[str] = mem_line.split()

        if len(fields) < 7:
            raise RuntimeError(
                f"Unexpected free output: expected >= 7 fields, got {len(fields)}"
            )

        # Index 1 is total, index 6 is available (includes reclaimable cache)
        try:
            total: int = int(fields[1])
        except ValueError:
            raise RuntimeError(f"Could not parse total memory from free output: '{fields[1]}' in line: {mem_line}")

        try:
            available: int = int(fields[6])
        except ValueError:
            raise RuntimeError(f"Could not parse available memory from free output: '{fields[6]}' in line: {mem_line}")

        # Guard against zero/negative total to avoid ZeroDivisionError
        if total <= 0:
            raise RuntimeError(f"Unexpected total memory value: {total}")

        # Calculate percentage usage
        used_pct: int = round(((total - available) / total) * 100)

        # Convert to GiB for the dynamic description
        used_gi: int = round((total - available) / (1024 ** 3))
        total_gi: int = round(total / (1024 ** 3))

        # Show actual values in the result so no conversion is needed
        self._dynamic_description = f"Memory usage on admin host ({used_gi}Gi used of {total_gi}Gi)"

        # Summarize for the health report
        self._health_info = f"Admin host using {used_pct}% memory ({used_gi}Gi of {total_gi}Gi)"

        return used_pct
