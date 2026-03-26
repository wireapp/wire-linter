"""Gets the RabbitMQ version from rabbitmqctl cluster_status.

We report back what version's running, good for tracking and support.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.terminal import ANSI_ESCAPE


class RabbitmqVersion(BaseTarget):
    """Gets the RabbitMQ version.

    Connects to a datanode via SSH and parses the version
    from rabbitmqctl cluster_status output.
    """

    # Uses SSH to reach RabbitMQ nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ version"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "We need to know what version's running for support and compatibility. "
            "Unsupported versions might have bugs or security problems."
        )

    def collect(self) -> str:
        """Get RabbitMQ version from cluster_status output.

        Returns:
            RabbitMQ version string.

        Raises:
            RuntimeError: If version cannot be determined.
        """
        self.terminal.step("Checking RabbitMQ version...")

        # Use whatever RabbitMQ host is configured
        result = self.run_db_command(
            self.config.databases.rabbitmq,
            "sudo rabbitmqctl cluster_status 2>/dev/null"
            " || sudo rabbitmqctl version 2>/dev/null",
        )

        # rabbitmqctl throws colors and bold at us, strip 'em out
        output: str = ANSI_ESCAPE.sub('', result.stdout).strip()

        # Try "RabbitMQ 3.9.27 on Erlang ..." format (from Versions section)
        match = re.search(r"RabbitMQ\s+(\d+\.\d+[\.\d]*)", output)
        if match:
            version: str = match.group(1)
            self._health_info = f"RabbitMQ {version}"
            return version

        # Try "RabbitMQ version: 3.12.0" (newer format)
        match2 = re.search(r"RabbitMQ\s+version[:\s]*(\S+)", output, re.IGNORECASE)
        if match2:
            version = match2.group(1)
            self._health_info = f"RabbitMQ {version}"
            return version

        # Try Erlang format: {rabbit,"RabbitMQ","3.9.27"}
        match3 = re.search(r"rabbit[,\s]+\"?(\d+\.\d+[\.\d]*)", output)
        if match3:
            version = match3.group(1)
            self._health_info = f"RabbitMQ {version}"
            return version

        # Or just a bare version number from "rabbitmqctl version"
        for line in output.split("\n"):
            stripped: str = line.strip()
            if stripped and re.fullmatch(r"\d+\.\d+[.\d]*", stripped):
                self._health_info = f"RabbitMQ {stripped}"
                return stripped

        raise RuntimeError("Could not determine RabbitMQ version")
