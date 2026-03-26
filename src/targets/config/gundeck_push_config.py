"""Detects push notification mode from gundeck ConfigMap.

Reads gundeck's aws.snsEndpoint and aws.sqsEndpoint to determine which of
the three push notification options is configured:

- Option A: Wire-managed SNS/SQS relay (recommended, standard public clients)
- Option B: Customer-managed SNS/SQS relay (requires custom client builds)
- Option C: WebSocket-only / fake-aws (no FCM/APNS, Android websocket only)

This is auto-detected, not a user question — Julia said "we won't ask the user,
we'll give them a report."
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class GundeckPushConfig(BaseTarget):
    """Detect push notification mode from gundeck ConfigMap.

    Reads aws.snsEndpoint and aws.sqsEndpoint to classify the deployment into
    one of three options (A: Wire-managed, B: customer-managed, C: websocket-only).
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Push notification mode (Option A/B/C)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire supports three push notification configurations: "
            "Option A (Wire-managed SNS/SQS relay — recommended), "
            "Option B (customer-managed SNS/SQS — requires custom client builds), "
            "Option C (WebSocket-only via fake-aws — no iOS push, Android battery drain). "
            "This target detects which is configured."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read gundeck ConfigMap and detect push notification mode.

        Returns:
            JSON string with push config details including the detected option.

        Raises:
            RuntimeError: If gundeck ConfigMap can't be fetched or parsed.
        """
        self.terminal.step("Reading gundeck ConfigMap for push notification config...")

        _result, cm_data = self.run_kubectl("configmap/gundeck")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Cannot fetch gundeck ConfigMap")

        gundeck_yaml_str: str = cm_data.get("data", {}).get("gundeck.yaml", "")
        if not gundeck_yaml_str:
            raise RuntimeError("gundeck ConfigMap missing gundeck.yaml")

        try:
            gundeck_config: dict[str, Any] = parse_yaml(gundeck_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Cannot parse gundeck.yaml: {e}") from e

        # Extract AWS endpoint configuration
        sns_endpoint: str = str(get_nested(gundeck_config, "aws.snsEndpoint", "") or "")
        sqs_endpoint: str = str(get_nested(gundeck_config, "aws.sqsEndpoint", "") or "")
        region: str = str(get_nested(gundeck_config, "aws.region", "") or "")
        account: str = str(get_nested(gundeck_config, "aws.account", "") or "")
        arn_env: str = str(get_nested(gundeck_config, "aws.arnEnv", "") or "")
        queue_name: str = str(get_nested(gundeck_config, "aws.queueName", "") or "")

        # Detect if this is fake-aws (Option C: websocket-only)
        is_fake_aws: bool = (
            "fake-aws" in sns_endpoint.lower()
            or "fake-aws" in sqs_endpoint.lower()
        )

        # Classify into Option A, B, or C
        # Option C: fake-aws endpoints (websocket-only, no real push)
        # Option A vs B: both use real AWS, but we can't definitively tell them
        # apart from config alone. We flag the distinction based on whether the
        # account looks like a dummy/placeholder (Option C leftovers) or real.
        if is_fake_aws:
            option: str = "C"
            option_label: str = "WebSocket-only (fake-aws)"
        else:
            option = "A_or_B"
            option_label = "Real AWS (FCM/APNS enabled)"
            # If the account is a known placeholder, it's likely misconfigured
            if account in ("123456789012", "000000000000", ""):
                option_label += " — account ID looks like a placeholder"

        result: dict[str, Any] = {
            "sns_endpoint": sns_endpoint,
            "sqs_endpoint": sqs_endpoint,
            "region": region,
            "account": account,
            "arn_env": arn_env,
            "queue_name": queue_name,
            "is_fake_aws": is_fake_aws,
            "option": option,
            "option_label": option_label,
        }

        if is_fake_aws:
            self._health_info = (
                f"Option C: WebSocket-only (fake-aws). "
                f"SNS: {sns_endpoint}, SQS: {sqs_endpoint}"
            )
        else:
            self._health_info = (
                f"Option A/B: Real AWS (FCM/APNS enabled). "
                f"Region: {region}, Account: {account}"
            )

        return json.dumps(result)
