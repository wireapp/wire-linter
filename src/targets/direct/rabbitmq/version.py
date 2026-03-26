"""Gets the RabbitMQ version via kubectl exec.

Kubectl-based alternative to the SSH version in databases/rabbitmq/version.py.
Runs rabbitmqctl inside the RabbitMQ pod and parses the version from
the output. Tries cluster_status first, falls back to rabbitmqctl version.
"""

from __future__ import annotations

# External
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.terminal import ANSI_ESCAPE
from src.targets.direct.rabbitmq._pod_finder import find_rabbitmq_pod


class DirectRabbitmqVersion(BaseTarget):
    """Gets the RabbitMQ version via kubectl exec.

    Finds the RabbitMQ pod, runs rabbitmqctl cluster_status (or version)
    inside it, and parses the version string from the output.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ version (kubectl)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "We need to know what version's running for support and compatibility. "
            "Unsupported versions might have bugs or security problems."
        )

    def collect(self) -> str:
        """Get RabbitMQ version from rabbitmqctl output.

        Tries cluster_status first, then falls back to rabbitmqctl version.
        Handles multiple output formats (human-readable and Erlang).

        Returns:
            RabbitMQ version string.

        Raises:
            RuntimeError: If version cannot be determined.
        """
        self.terminal.step("Checking RabbitMQ version via kubectl...")

        # Find the RabbitMQ pod (searches all namespaces)
        pod_name, namespace = find_rabbitmq_pod(self)

        # Try cluster_status first (it includes version info), fall back to version
        result = self.run_kubectl_raw([
            "exec", pod_name, "-n", namespace, "--",
            "sh", "-c",
            "rabbitmqctl cluster_status 2>/dev/null"
            " || rabbitmqctl version 2>/dev/null",
        ])

        # rabbitmqctl throws colors and bold at us, strip 'em out
        output: str = ANSI_ESCAPE.sub('', result.stdout).strip()

        # Try "RabbitMQ 3.9.27 on Erlang ..." format (from Versions section)
        match: re.Match[str] | None = re.search(
            r"RabbitMQ\s+(\d+\.\d+[\.\d]*)", output,
        )
        if match:
            version: str = match.group(1)
            self._health_info = f"RabbitMQ {version}"
            return version

        # Try "RabbitMQ version: 3.12.0" (newer format)
        match2: re.Match[str] | None = re.search(
            r"RabbitMQ\s+version[:\s]*(\S+)", output, re.IGNORECASE,
        )
        if match2:
            version = match2.group(1)
            self._health_info = f"RabbitMQ {version}"
            return version

        # Try Erlang format: {rabbit,"RabbitMQ","3.9.27"}
        match3: re.Match[str] | None = re.search(
            r"rabbit[,\s]+\"?(\d+\.\d+[\.\d]*)", output,
        )
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
