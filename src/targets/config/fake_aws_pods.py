"""Checks if fake-aws-sns and fake-aws-sqs pods are running.

In websocket-only deployments, gundeck talks to fake-aws pods instead of real
AWS. If these pods are not running, gundeck can't start and notifications break.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class FakeAwsPods(BaseTarget):
    """Check if fake-aws-sns and fake-aws-sqs pods are running.

    Scans pods for names matching fake-aws-sns and fake-aws-sqs.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Fake-AWS pods status (SNS and SQS)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "In websocket-only deployments (no FCM/APNS push), gundeck uses in-cluster "
            "fake-aws-sns and fake-aws-sqs pods as mock AWS endpoints. If these pods "
            "aren't running, gundeck can't initialize and all notifications break."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Search for fake-aws pods and report their status.

        Returns:
            JSON string with fake-aws pod status.
        """
        self.terminal.step("Searching for fake-aws-sns and fake-aws-sqs pods...")

        _result, data = self.run_kubectl("pods")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch pod list")

        items: list[dict[str, Any]] = data.get("items", [])

        fake_sns_pods: list[str] = []
        fake_sqs_pods: list[str] = []
        fake_sns_running: bool = False
        fake_sqs_running: bool = False

        for pod in items:
            name: str = pod.get("metadata", {}).get("name", "")
            phase: str = pod.get("status", {}).get("phase", "")

            if "fake-aws-sns" in name.lower():
                fake_sns_pods.append(name)
                if phase == "Running":
                    fake_sns_running = True

            if "fake-aws-sqs" in name.lower():
                fake_sqs_pods.append(name)
                if phase == "Running":
                    fake_sqs_running = True

        result: dict[str, Any] = {
            "fake_sns_running": fake_sns_running,
            "fake_sqs_running": fake_sqs_running,
            "fake_sns_pods": fake_sns_pods,
            "fake_sqs_pods": fake_sqs_pods,
        }

        if fake_sns_running and fake_sqs_running:
            self._health_info = "Both fake-aws-sns and fake-aws-sqs are running"
        elif not fake_sns_pods and not fake_sqs_pods:
            self._health_info = "No fake-aws pods found in the cluster"
        else:
            parts: list[str] = []
            if not fake_sns_running:
                parts.append("fake-aws-sns: NOT running")
            if not fake_sqs_running:
                parts.append("fake-aws-sqs: NOT running")
            self._health_info = ", ".join(parts)

        return json.dumps(result)
