"""Checks RabbitMQ cluster health by running rabbitmqctl cluster_status.

Parses the output to see if nodes are running and if there are alarms.
Tells you if things are healthy, have alarms, or just broken. Connects
to whatever RabbitMQ host is configured (usually colocated with Cassandra).
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.terminal import ANSI_ESCAPE


class RabbitmqClusterStatus(BaseTarget):
    """Checks RabbitMQ cluster health.

    Connects to a datanode via SSH, runs rabbitmqctl cluster_status,
    and interprets the output to determine overall cluster health.
    """

    # Uses SSH to reach RabbitMQ nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ cluster status"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "We need running nodes and no alarms. No nodes = the broker's down. "
            "Alarms mean we're out of disk or memory and nothing can get through."
        )

    def collect(self) -> str:
        """Check RabbitMQ cluster health by inspecting running nodes and alarms.

        Returns:
            "healthy" if nodes are running and no alarms are active,
            "alarms" if nodes are running but alarms are present,
            "unhealthy" if no running nodes were detected.

        Raises:
            RuntimeError: Not raised directly; returns "unhealthy" on bad output.
        """
        # Tell the operator what we're up to
        self.terminal.step("Checking RabbitMQ cluster status...")

        # Try without sudo first — some systems run rabbitmqctl as a normal user,
        # and sudo may hang or fail silently on hardened systems without passwordless sudo
        result = self.run_db_command(
            self.config.databases.rabbitmq,
            "rabbitmqctl cluster_status",
        )

        # rabbitmqctl throws colors and bold at us, strip it out
        output: str = ANSI_ESCAPE.sub('', result.stdout).strip()

        # If non-sudo failed (permissions error or empty output), retry with sudo
        if not output or not result.success:
            result = self.run_db_command(
                self.config.databases.rabbitmq,
                "sudo rabbitmqctl cluster_status",
            )
            output = ANSI_ESCAPE.sub('', result.stdout).strip()

        # Detect whether the output reports any running nodes at all
        has_running: bool = "Running Nodes" in output or "running_nodes" in output

        # Default to no alarms until we find evidence of one
        has_alarms: bool = False

        # Look for the Alarms section in two ways:
        # 1) Human-readable format has a standalone "Alarms" header line (more reliable)
        # 2) Erlang format embeds "alarms" as a keyword inside tuples (less reliable)
        # We try the human-readable header first to avoid false matches on
        # Erlang terms like {alarms,[]} that appear in earlier sections.
        output_lines: list[str] = output.split("\n")
        alarm_line_index: int = -1

        # Search for a standalone "Alarms" line (human-readable format header)
        for i, line in enumerate(output_lines):
            if line.strip() == "Alarms":
                alarm_line_index = i
                break

        if alarm_line_index != -1:
            # Human-readable format: content starts on the line after the header
            alarm_section = "\n".join(output_lines[alarm_line_index + 1:])
        else:
            # Fall back to Erlang-style keyword, but use the LAST occurrence
            # since the actual Alarms section appears near the end of the output
            lower_output: str = output.lower()
            last_pos: int = lower_output.rfind("alarms")
            if last_pos != -1:
                alarm_section = output[last_pos + len("alarms"):]
            else:
                alarm_section = ""

        if alarm_section:

            # Scan lines after the keyword. Sections go: header → blank → content → blank → next.
            # A blank line after non-blank stuff marks the end.
            # Note: we start at index 0 not [1:] because Erlang format has content
            # on the same line as the keyword (e.g. ",[{memory_alarm,'rabbit@node1'}]}")
            alarm_lines: list[str] = alarm_section.split("\n")
            seen_content: bool = False

            for line in alarm_lines:
                stripped: str = line.strip()

                # Blank line after content means we're done with Alarms
                if not stripped and seen_content:
                    break

                # Skip blank lines and standalone commas from Erlang
                if not stripped or stripped == ",":
                    continue

                seen_content = True

                # "(none)" means no alarms in the new format
                if stripped == "(none)":
                    break

                # "[]" or ",[]..." in Erlang means no alarms
                if stripped.startswith(",[]") or stripped.startswith("[]"):
                    break

                # Anything else that isn't a Node: label is an alarm entry
                if not stripped.startswith("Node:"):
                    has_alarms = True
                    break

        # Build the status result
        if has_running and not has_alarms:
            self._health_info = "Nodes running, no alarms"
            return "healthy"
        elif has_running and has_alarms:
            self._health_info = "Nodes running but alarms active"
            return "alarms"

        self._health_info = "No running nodes detected"
        return "unhealthy"
