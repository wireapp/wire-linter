"""Gets the PostgreSQL version running on the datanode.

Hits psql to find out what version is actually running. Good to know
for compatibility and support issues.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class PostgresqlVersion(BaseTarget):
    """Gets the PostgreSQL version.

    Connects to the PostgreSQL host via SSH and queries the server
    version string.
    """

    # Uses SSH to reach PostgreSQL nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "PostgreSQL version"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "We need to know what version's running. EOL versions don't get "
            "security patches and might not have features we need."
        )

    def collect(self) -> str:
        """Get the PostgreSQL version from the datanode.

        Returns:
            PostgreSQL version string.

        Raises:
            RuntimeError: If the version cannot be determined.
        """
        self.terminal.step("Checking PostgreSQL version...")

        # Try psql first, it's usually the cleanest
        result = self.run_db_command(
            self.config.databases.postgresql,
            "sudo -u postgres psql -t -c 'SELECT version()' 2>/dev/null"
            " || psql --version 2>/dev/null",
        )

        output: str = result.stdout.strip()

        if not output:
            raise RuntimeError("Could not determine PostgreSQL version")

        # psql returns a long string like "PostgreSQL 15.4 (Ubuntu 15.4-1.pgdg22.04+1) on x86_64..."
        # or just "psql (PostgreSQL) 15.4" from --version.
        # Just grab the first line and call it a day.
        version: str = output.split("\n")[0].strip()

        self._health_info = version[:80]
        return version
