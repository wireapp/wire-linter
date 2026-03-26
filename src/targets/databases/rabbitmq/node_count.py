"""Counts running RabbitMQ nodes by parsing rabbitmqctl cluster_status.

We extract the Running Nodes section first (handles both Erlang format
{running_nodes,[...]} and modern format), then hunt for rabbit@ entries
in just that section. Uses whatever RabbitMQ host is configured.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget


class RabbitmqNodeCount(BaseTarget):
    """Counts RabbitMQ nodes.

    Connects to a datanode via SSH, runs rabbitmqctl cluster_status,
    and counts node identifiers in the Running Nodes section only.
    """

    # Uses SSH to reach RabbitMQ nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Number of RabbitMQ nodes"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "We count how many nodes are actually running. Fewer than expected "
            "means a broker went down, and you lose throughput and failover cover."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement for the returned value."""
        return "nodes"

    def _extract_running_nodes_section(self, output: str) -> str:
        """Extract the Running Nodes section from rabbitmqctl output.

        Handles both legacy Erlang ({running_nodes,[...]}) and modern
        ('Running Nodes' header) formats.

        Args:
            output: Full stdout from rabbitmqctl cluster_status.

        Returns:
            Text containing just the running nodes part.

        Raises:
            RuntimeError: If the Running Nodes section isn't found.
        """
        # Erlang format: {running_nodes,[...]}, \s* for optional whitespace,
        # re.DOTALL so it works across lines for big clusters
        erlang_match: re.Match[str] | None = re.search(
            r"\{running_nodes,\s*\[([^\]]*)\]",
            output,
            re.DOTALL,
        )
        if erlang_match:
            return erlang_match.group(1)

        # Modern format: "Running Nodes" header, then one node per line,
        # stops at a blank line or next section header
        lines: list[str] = output.splitlines()
        in_section: bool = False
        section_lines: list[str] = []

        for line in lines:
            stripped: str = line.strip()

            # Substring match to handle weird formatting or case variations
            if "running nodes" in stripped.lower():
                in_section = True
                continue

            if in_section:
                # A non-blank line not starting with "rabbit@" = new section, we're done
                if stripped and not stripped.startswith("rabbit@"):
                    break
                section_lines.append(stripped)

        section_text: str = "\n".join(section_lines)
        if section_text.strip():
            return section_text

        # Include first 200 chars to help debug weird output
        snippet: str = output[:200].replace("\n", " ")
        raise RuntimeError(
            f"Could not find Running Nodes section in rabbitmqctl output. "
            f"Raw output (first 200 chars): {snippet!r}"
        )

    def collect(self) -> int:
        """Count the number of running RabbitMQ nodes.

        Returns:
            Integer count of rabbit@ entries in the Running Nodes section only.

        Raises:
            RuntimeError: If the Running Nodes section or node entries cannot be found.
        """
        # Tell the operator what we're doing
        self.terminal.step("Counting RabbitMQ nodes...")

        # Use whatever RabbitMQ host is configured
        result = self.run_db_command(
            self.config.databases.rabbitmq,
            "sudo rabbitmqctl cluster_status",
        )

        output: str = result.stdout.strip()

        # Extract just the Running Nodes section so we don't count Disk Nodes or other stuff
        running_section: str = self._extract_running_nodes_section(output)

        # Use [\w.-]+ instead of \S+ to avoid grabbing Erlang punctuation
        nodes: list[str] = re.findall(r"rabbit@[\w.-]+", running_section)

        # Zero nodes = either parsing failed or cluster's really broken
        count: int = len(nodes)
        if count == 0:
            snippet: str = running_section[:200].replace("\n", " ")
            raise RuntimeError(
                f"No rabbit@ entries found in Running Nodes section. "
                f"Section content: {snippet!r}"
            )

        # Summarize what we found for the health report
        self._health_info = f"RabbitMQ cluster has {count} running node{'s' if count != 1 else ''}"

        return count
