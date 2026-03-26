"""Checks RabbitMQ cluster health via kubectl exec.

Kubectl-based alternative to the SSH version in databases/rabbitmq/cluster_status.py.
Runs rabbitmqctl cluster_status inside the RabbitMQ pod and parses the output
to determine if the cluster is healthy, has alarms, or is unhealthy.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.terminal import ANSI_ESCAPE
from src.targets.direct.rabbitmq._pod_finder import find_rabbitmq_pod


class DirectRabbitmqClusterStatus(BaseTarget):
    """Checks RabbitMQ cluster health via kubectl exec.

    Finds the RabbitMQ pod via label selectors, runs rabbitmqctl cluster_status
    inside it, and interprets the output to determine overall cluster health.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ cluster status (kubectl)"

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
        """
        # Tell the operator what we're up to
        self.terminal.step("Checking RabbitMQ cluster status via kubectl...")

        # Find the RabbitMQ pod (searches all namespaces)
        pod_name, namespace = find_rabbitmq_pod(self)

        # Run rabbitmqctl cluster_status inside the pod (no sudo needed in container)
        result = self.run_kubectl_raw([
            "exec", pod_name, "-n", namespace, "--",
            "rabbitmqctl", "cluster_status",
        ])

        # rabbitmqctl throws colors and bold at us, strip it out
        output: str = ANSI_ESCAPE.sub('', result.stdout).strip()

        # Detect whether the output reports any running nodes at all
        has_running: bool = "Running Nodes" in output or "running_nodes" in output

        # Default to no alarms until we find evidence of one
        has_alarms: bool = False

        # Only look at the Alarms section if it's there.
        # Works with both the new human format ("Alarms") and old Erlang ("alarms")
        lower_output: str = output.lower()
        if "alarms" in lower_output:
            # Extract from the keyword position to keep exact casing
            alarms_pos: int = lower_output.index("alarms")
            alarm_section: str = output[alarms_pos + len("alarms"):]

            # Scan lines after the keyword. Sections go: header -> blank -> content -> blank -> next.
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
