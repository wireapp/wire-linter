"""Tests connectivity to AWS SQS endpoint from inside the Gundeck pod.

Same approach as aws_sns_reachability — uses curl matching Julia's documented
check command. Any HTTP response (even 4xx) confirms connectivity.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class AwsSqsReachability(BaseTarget):
    """Test connectivity to AWS SQS from inside the Gundeck pod.

    Only runs when push notifications use real AWS and internet is available.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "AWS SQS reachability from Gundeck pod"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "When using real AWS for push notifications (Option A or B), gundeck "
            "also needs access to SQS for device event feedback (uninstalled apps, "
            "expired push tokens)."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test connectivity to AWS SQS from inside the Gundeck pod.

        Returns:
            JSON string with reachability details.

        Raises:
            NotApplicableError: If fake-aws is in use or no internet.
        """
        if not self.config.options.has_internet:
            raise NotApplicableError("No internet access declared")

        self.terminal.step("Detecting push notification mode from gundeck config...")

        try:
            _result, cm_data = self.run_kubectl("configmap/gundeck")
            if not isinstance(cm_data, dict):
                raise NotApplicableError("Cannot read gundeck ConfigMap")

            gundeck_yaml_str: str = cm_data.get("data", {}).get("gundeck.yaml", "")
            if not gundeck_yaml_str:
                raise NotApplicableError("gundeck ConfigMap missing gundeck.yaml")

            gundeck_config: dict[str, Any] = parse_yaml(gundeck_yaml_str)
            sqs_endpoint: str = str(get_nested(gundeck_config, "aws.sqsEndpoint", "") or "")
            region: str = str(get_nested(gundeck_config, "aws.region", "eu-west-1") or "eu-west-1")

        except (ValueError, RuntimeError) as e:
            raise NotApplicableError(f"Cannot determine push mode: {e}")

        if "fake-aws" in sqs_endpoint.lower():
            raise NotApplicableError("Using fake-aws (Option C: websocket-only) — no real AWS to check")

        target_host: str = f"sqs.{region}.amazonaws.com"
        self.terminal.step(f"Testing connectivity to https://{target_host} from Gundeck pod...")

        reachable: bool = False
        error_msg: str = ""
        http_status: int = 0

        try:
            _result, pods_data = self.run_kubectl("pods")
            if not isinstance(pods_data, dict):
                raise RuntimeError("Cannot list pods")

            gundeck_pod: str = ""
            for pod in pods_data.get("items", []):
                name: str = pod.get("metadata", {}).get("name", "")
                phase: str = pod.get("status", {}).get("phase", "")
                if "gundeck" in name.lower() and phase == "Running":
                    gundeck_pod = name
                    break

            if not gundeck_pod:
                raise RuntimeError("No running gundeck pod found")

            # Match Julia's documented command: curl -v --max-time 10 https://sqs.<region>.amazonaws.com
            namespace: str = self.config.cluster.kubernetes_namespace
            curl_cmd: str = (
                f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "
                f"https://{target_host}/"
            )
            exec_cmd: str = f"kubectl exec {gundeck_pod} -n {namespace} -- {curl_cmd}"

            cmd_result = self._run_shell_command(exec_cmd)
            if cmd_result and cmd_result.returncode == 0:
                status_str: str = cmd_result.stdout.strip().strip("'\"")
                if status_str.isdigit():
                    http_status = int(status_str)
                    reachable = http_status > 0
                else:
                    reachable = True
            elif cmd_result:
                error_msg = cmd_result.stderr.strip() or "curl command failed"
                # Fall back to wget if curl not available
                if "not found" in error_msg.lower():
                    wget_cmd: str = f"wget -q -O /dev/null --timeout=10 --spider https://{target_host}/"
                    exec_cmd = f"kubectl exec {gundeck_pod} -n {namespace} -- {wget_cmd}"
                    cmd_result = self._run_shell_command(exec_cmd)
                    reachable = cmd_result.returncode == 0 if cmd_result else False
                    if not reachable and cmd_result:
                        error_msg = cmd_result.stderr.strip() or "wget failed"

        except RuntimeError as e:
            error_msg = str(e)

        result: dict[str, Any] = {
            "target_host": target_host,
            "reachable": reachable,
            "region": region,
            "http_status": http_status,
            "error": error_msg,
        }

        if reachable:
            status_info: str = f" (HTTP {http_status})" if http_status else ""
            self._health_info = f"AWS SQS reachable: {target_host}{status_info}"
        else:
            self._health_info = f"AWS SQS NOT reachable: {target_host} — {error_msg}"

        return json.dumps(result)
