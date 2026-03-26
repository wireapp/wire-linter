"""Checks RabbitMQ queue depths for message backlogs.

If queues build up, consumers are either down or can't keep up, and
messages pile up. We use rabbitmqctl list_queues to check this.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


# Queues with more messages than this are flagged
_DEPTH_THRESHOLD: int = 1000


class RabbitmqQueueDepth(BaseTarget):
    """Checks RabbitMQ queue depths for backlogs.

    Queries queue message counts and reports any with significant
    backlogs that might indicate consumer issues.
    """

    # Uses SSH to reach RabbitMQ nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ queue depth (message backlog)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "When consumers are down or drowning, queues pile up and messages "
            "get delayed. We flag queues over 1000 messages as backlogs."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the collected value."""
        return "messages"

    def collect(self) -> int:
        """Check RabbitMQ queue depths and return the maximum.

        Returns:
            Maximum message count across all queues.

        Raises:
            RuntimeError: If queue information cannot be retrieved.
        """
        self.terminal.step("Checking RabbitMQ queue depths...")

        # Try without sudo first — some systems run rabbitmqctl as a normal user,
        # and sudo may hang or fail silently on hardened systems without passwordless sudo
        result = self.run_db_command(
            self.config.databases.rabbitmq,
            "rabbitmqctl list_queues name messages",
        )

        output: str = result.stdout.strip()

        # If non-sudo failed (permissions error or empty output), retry with sudo
        if not output or not result.success:
            result = self.run_db_command(
                self.config.databases.rabbitmq,
                "sudo rabbitmqctl list_queues name messages",
            )
            output = result.stdout.strip()

        if not output:
            # Include stderr in the error message so operators can see the real cause
            # (e.g. "sudo: a password is required", "command not found")
            stderr_hint: str = result.stderr.strip()
            detail: str = f" (stderr: {stderr_hint})" if stderr_hint else ""
            raise RuntimeError(
                f"rabbitmqctl list_queues returned no output{detail}"
            )

        # Check for the "Listing queues" header. If rabbitmqctl fails (broker down,
        # auth error), it returns non-empty garbage without this header, and we'd
        # end up with a bogus "0 queues" result.
        if "listing queues" not in output.lower():
            raise RuntimeError(
                f"rabbitmqctl list_queues did not return expected output: {output}"
            )

        max_depth: int = 0
        total_messages: int = 0
        queue_count: int = 0
        deep_queues: list[str] = []

        for line in output.split("\n"):
            # Skip header and timeout lines, they're not queues
            stripped: str = line.strip()
            if not stripped or "listing" in stripped.lower() or "timeout" in stripped.lower():
                continue

            parts: list[str] = stripped.split()
            if len(parts) >= 2:
                queue_name: str = parts[0]
                try:
                    messages: int = int(parts[1])
                except ValueError:
                    continue

                queue_count += 1
                total_messages += messages

                if messages > max_depth:
                    max_depth = messages

                if messages > _DEPTH_THRESHOLD:
                    deep_queues.append(f"{queue_name} ({messages})")

        if deep_queues:
            self._health_info = (
                f"{len(deep_queues)} queue(s) with >{_DEPTH_THRESHOLD} messages: "
                f"{', '.join(deep_queues[:5])}"
            )
        else:
            self._health_info = f"{queue_count} queues, {total_messages} total messages, max depth {max_depth}"

        return max_depth
