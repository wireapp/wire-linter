"""Check if email delivery is working.

No email means no password resets, no account verification that's bad.
Looks for SMTP, fake-aws-sns, or email pods to confirm it's running.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class SmtpService(BaseTarget):
    """Check if email service is actually running.

    We hunt for SMTP, fake-aws-sns, or email pods to see if email delivery works.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "SMTP/email service running"

    @property
    def explanation(self) -> str:
        """Why we care about this."""
        return (
            "No email means account verification breaks and password resets don't work. "
            "We're good if any of those email/SMTP pods are running."
        )

    @property
    def unit(self) -> str:
        """No unit this is a yes/no check."""
        return ""

    def collect(self) -> bool:
        """See if any email pods are actually running."""
        self.terminal.step("Checking SMTP/email service...")

        # Grab list of pods from kubectl
        cmd_result, data = self.run_kubectl("pods")

        if data is None:
            raise RuntimeError("Failed to query pods from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        smtp_pods: list[str] = []
        for pod in items:
            name: str = pod.get("metadata", {}).get("name", "")
            phase: str = pod.get("status", {}).get("phase", "")

            # Look for SMTP, fake-aws-sns, email, SES pods
            if phase == "Running" and (
                "smtp" in name.lower()
                or "fake-aws-sns" in name.lower()
                or "email" in name.lower()
                or "ses" in name.lower()
            ):
                smtp_pods.append(name)

        has_smtp: bool = len(smtp_pods) > 0

        if has_smtp:
            self._health_info = f"Email service running: {', '.join(smtp_pods)}"
        else:
            self._health_info = "No SMTP/email pods found running"

        return has_smtp
