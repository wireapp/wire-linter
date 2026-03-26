"""Checks RabbitMQ queue depths for message backlogs via kubectl exec.

Kubectl-based alternative to the SSH version in databases/rabbitmq/queue_depth.py.
Runs rabbitmqctl list_queues inside the RabbitMQ pod and checks for queues
with significant message backlogs that might indicate consumer issues.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.targets.direct.rabbitmq._pod_finder import find_rabbitmq_pod


# Queues with more messages than this are flagged
_DEPTH_THRESHOLD: int = 1000


class DirectRabbitmqQueueDepth(BaseTarget):
    """Checks RabbitMQ queue depths for backlogs via kubectl exec.

    Finds the RabbitMQ pod, queries queue message counts, and reports
    any with significant backlogs that might indicate consumer issues.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ queue depth (kubectl)"

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
        self.terminal.step("Checking RabbitMQ queue depths via kubectl...")

        # Find the RabbitMQ pod (searches all namespaces)
        pod_name, namespace = find_rabbitmq_pod(self)

        # List all queues with their message counts (no sudo needed in container)
        result = self.run_kubectl_raw([
            "exec", pod_name, "-n", namespace, "--",
            "rabbitmqctl", "list_queues", "name", "messages",
        ])

        output: str = result.stdout.strip()

        if not output:
            raise RuntimeError("rabbitmqctl list_queues returned no output")

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
            # Parse tab-separated output: only lines with exactly 2 tab-separated
            # fields (queue name + message count) are valid data rows. This correctly
            # handles queue names containing words like "timeout" or "listing" that
            # would be falsely skipped by naive substring matching.
            parts: list[str] = line.split("\t")
            if len(parts) != 2:
                continue

            queue_name: str = parts[0].strip()
            if not queue_name:
                continue

            try:
                messages: int = int(parts[1].strip())
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
