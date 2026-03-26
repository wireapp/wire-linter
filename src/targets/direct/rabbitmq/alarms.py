"""Checks for RabbitMQ memory and disk alarms via kubectl exec.

Kubectl-based alternative to the SSH version in databases/rabbitmq/alarms.py.
When alarms fire, RabbitMQ locks up and stops all message flow. This is
more specific than cluster_status -- we're really just hunting for alarms.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.terminal import ANSI_ESCAPE
from src.targets.direct.rabbitmq._pod_finder import find_rabbitmq_pod


class DirectRabbitmqAlarms(BaseTarget):
    """Checks RabbitMQ for active memory/disk alarms via kubectl exec.

    Finds the RabbitMQ pod, runs rabbitmqctl status inside it, and
    parses the alarms section for active memory or disk resource alarms.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ memory/disk alarms (kubectl)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "If memory or disk alarms go off, RabbitMQ blocks everything. "
            "We're good when there's no alarms at all."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement -- empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check for active RabbitMQ alarms.

        Returns:
            True if no alarms are active, False if alarms are present.
        """
        self.terminal.step("Checking RabbitMQ alarms via kubectl...")

        # Find the RabbitMQ pod (searches all namespaces)
        pod_name, namespace = find_rabbitmq_pod(self)

        # Get the status from rabbitmqctl (no sudo needed in container)
        result = self.run_kubectl_raw([
            "exec", pod_name, "-n", namespace, "--",
            "rabbitmqctl", "status",
        ])

        # rabbitmqctl throws ANSI codes at us (bold, colors), strip 'em out
        # or we'll fail to match headers
        output: str = ANSI_ESCAPE.sub('', result.stdout).strip()
        lines: list[str] = output.split("\n")

        alarm_indicators: list[str] = []
        seen: set[str] = set()

        # Signal 1: look for alarm keywords in Erlang format.
        # Erlang spits out {alarms,[{resource_limit,memory,...}]} on one line;
        # these keywords are reliable no matter how the output's structured.
        for line in lines:
            stripped: str = line.strip()
            is_keyword_alarm: bool = (
                "{alarm,"          in stripped
                or "resource_alarm"  in stripped
                or "resource_limit"  in stripped
                or ("{alarms,["    in stripped and "{alarms,[]}" not in stripped)
            )
            if is_keyword_alarm:
                candidate: str = stripped[:80]
                if candidate not in seen:
                    seen.add(candidate)
                    alarm_indicators.append(candidate)

        # Signal 2: look for the Alarms section in human-readable format.
        # rabbitmqctl puts a blank line after "Alarms", then the alarm names.
        # One-pass gets confused by blank lines, so we find the header first,
        # then scan from there, skipping blanks until we hit a new section.
        header_index: int | None = None
        for idx, line in enumerate(lines):
            if line.strip() in ("Alarms", "alarms", "Alarms:", "alarms:"):
                header_index = idx
                break

        # These are the known section headers that come after Alarms in rabbitmqctl.
        # If we hit one, we've left the Alarms section. Other root-level lines
        # get treated as alarm content in case new alarm types show up.
        known_section_headers: frozenset[str] = frozenset({
            "nodes",
            "running nodes",
            "disk nodes",
            "ram nodes",
            "listeners",
            "network partitions",
            "feature flags",
            "summary",
            "runtime",
            "plugins",
            "data directory",
            "config files",
            "log file(s)",
            "status of node",
        })

        if header_index is not None:
            for line in lines[header_index + 1:]:
                stripped = line.strip()

                # Blank lines between the header and the alarms are fine
                if not stripped:
                    continue

                # Explicit "no alarms" marker, stop scanning
                if stripped in ("(none)", "[]"):
                    break

                is_at_root: bool = len(line) > 0 and not line[0].isspace()

                if is_at_root:
                    # It's a known section header, we're done with Alarms
                    if stripped.rstrip(":").lower() in known_section_headers:
                        break
                    # Any other root-level line is an alarm
                    candidate = stripped[:80]
                    if candidate not in seen:
                        seen.add(candidate)
                        alarm_indicators.append(candidate)
                else:
                    # Indented line might be alarm details
                    is_alarm_content: bool = (
                        "memory" in stripped.lower() or "disk" in stripped.lower()
                    )
                    if is_alarm_content:
                        candidate = stripped[:80]
                        if candidate not in seen:
                            seen.add(candidate)
                            alarm_indicators.append(candidate)

        no_alarms: bool = len(alarm_indicators) == 0

        if no_alarms:
            self._health_info = "No memory/disk alarms active"
        else:
            self._health_info = f"ALARMS ACTIVE: {'; '.join(alarm_indicators[:3])}"

        return no_alarms
