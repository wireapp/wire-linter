"""Detects email delivery configuration from brig ConfigMap.

Julia said: "For email, we're not asking them, our system should be able to
gather that information directly." And: "Check if brig is configured to use
the SMTP service."

Brig supports two email delivery methods:
- SMTP: direct connection to a mail server (smtp.host, smtp.port, smtp.connType)
- AWS SES: Amazon Simple Email Service (useSES: true, emailSMS.email.sesEndpoint)

In demo environments, the demo-smtp pod provides a mock SMTP server.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class BrigEmailConfig(BaseTarget):
    """Detect email delivery configuration from brig ConfigMap.

    Reads smtp.host, smtp.connType, useSES, emailSMS settings to determine
    how brig sends emails (password resets, verification, invitations).
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Email delivery configuration (SMTP / SES)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Email is required for account verification, password resets, and team "
            "invitations. Brig can use SMTP (direct mail server) or AWS SES. If "
            "email is misconfigured, these critical user flows break."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read brig ConfigMap and detect email configuration.

        Returns:
            JSON string with email config details.

        Raises:
            RuntimeError: If brig ConfigMap can't be fetched or parsed.
        """
        self.terminal.step("Reading brig ConfigMap for email configuration...")

        _result, cm_data = self.run_kubectl("configmap/brig")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Cannot fetch brig ConfigMap")

        brig_yaml_str: str = cm_data.get("data", {}).get("brig.yaml", "")
        if not brig_yaml_str:
            raise RuntimeError("brig ConfigMap missing brig.yaml")

        try:
            brig_config: dict[str, Any] = parse_yaml(brig_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Cannot parse brig.yaml: {e}") from e

        # Check if using AWS SES
        use_ses: bool = bool(get_nested(brig_config, "useSES", False))

        # SMTP settings (used when not using SES)
        smtp_host: str = str(get_nested(brig_config, "smtp.host", "") or "")
        smtp_port: int = int(get_nested(brig_config, "smtp.port", 25) or 25)
        smtp_conn_type: str = str(get_nested(brig_config, "smtp.connType", "") or "")

        # SES settings
        ses_endpoint: str = str(
            get_nested(brig_config, "emailSMS.email.sesEndpoint", "") or ""
        )
        ses_queue: str = str(
            get_nested(brig_config, "emailSMS.email.sesQueue", "") or ""
        )

        # Email sender address
        email_sender: str = str(
            get_nested(brig_config, "emailSMS.general.emailSender", "") or ""
        )

        # Determine mode
        mode: str = "ses" if (use_ses or ses_endpoint) else "smtp"

        result: dict[str, Any] = {
            "mode": mode,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_conn_type": smtp_conn_type,
            "ses_endpoint": ses_endpoint,
            "ses_queue": ses_queue,
            "email_sender": email_sender,
            "use_ses": use_ses,
        }

        if mode == "ses":
            self._health_info = f"Email via AWS SES (endpoint: {ses_endpoint or 'default'})"
        elif smtp_host:
            self._health_info = (
                f"Email via SMTP ({smtp_host}:{smtp_port}, {smtp_conn_type or 'unknown'})"
            )
        else:
            self._health_info = "No email configuration found"

        return json.dumps(result)
