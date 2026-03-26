"""Checks that all RabbitMQ queues are durable.

Non-durable queues disappear when RabbitMQ restarts or fails over. Wire
services expect durable queues, so if one's non-durable (maybe from a failed
migration), we silently lose messages on the next restart. WPB-17723.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class RabbitmqQueuePersistence(BaseTarget):
    """Checks that all RabbitMQ queues are configured as durable.

    Lists all queues and their durability flag via rabbitmqctl. Returns
    the count of non-durable queues (0 means all queues are safe).
    """

    # Uses SSH to reach RabbitMQ nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ queue durability (all queues durable)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Non-durable queues vanish on restart, and Wire services don't know about it, "
            "so messages just disappear silently (WPB-17723)."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the collected value."""
        return "non-durable"

    def collect(self) -> int:
        """Count RabbitMQ queues that are not durable.

        Returns:
            Number of non-durable queues (0 = all queues are durable = healthy).

        Raises:
            RuntimeError: If queue durability information cannot be retrieved.
        """
        self.terminal.step("Checking RabbitMQ queue durability...")

        # Get the durable flag for each queue.
        # databases.rabbitmq defaults to the Cassandra IP for co-located setups
        # and uses the actual RabbitMQ broker IP for dedicated-broker setups.
        result = self.run_db_command(
            self.config.databases.rabbitmq,
            "sudo rabbitmqctl list_queues name durable 2>/dev/null"
            " || sudo rabbitmqctl list_queues --vhost / name durable 2>/dev/null",
        )

        output: str = result.stdout.strip()

        if not output:
            raise RuntimeError("rabbitmqctl list_queues returned no output")

        non_durable: list[str] = []
        durable_count: int = 0
        total_count: int = 0

        for line in output.split("\n"):
            stripped: str = line.strip()

            # Skip headers, timeouts, listing lines
            if (
                not stripped
                or stripped.lower().startswith("listing")
                or stripped.lower().startswith("timeout")
                or stripped == "name\tdurable"
                or stripped == "name  durable"
            ):
                continue

            parts: list[str] = stripped.split()

            # Format: queue_name  true|false
            if len(parts) < 2:
                continue

            queue_name: str = parts[0]
            durable_flag: str = parts[-1].lower()

            total_count += 1

            if durable_flag == "true":
                durable_count += 1
            elif durable_flag == "false":
                non_durable.append(queue_name)

        if total_count == 0:
            # No queues at all RabbitMQ may be empty or the command failed
            self._health_info = "No queues found (RabbitMQ may be empty)"
            return 0

        non_durable_count: int = len(non_durable)

        if non_durable_count == 0:
            self._health_info = (
                f"All {durable_count} queue(s) are durable"
            )
        else:
            shown: str = ", ".join(non_durable[:5])
            suffix: str = f" (+{non_durable_count - 5} more)" if non_durable_count > 5 else ""
            self._health_info = (
                f"{non_durable_count}/{total_count} queue(s) are NOT durable: "
                f"{shown}{suffix}"
            )

        return non_durable_count
