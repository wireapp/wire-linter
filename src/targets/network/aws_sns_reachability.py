"""Tests connectivity to AWS SNS endpoint from inside the Gundeck pod.

Julia's documentation specifies the check command:
  curl -v --max-time 10 https://sns.<region>.amazonaws.com

"Even a 4xx status is acceptable — it confirms TCP and TLS connectivity.
A connection timeout or TLS handshake failure indicates the endpoint is
not reachable from your network."

Only runs when gundeck is configured for real AWS (not fake-aws) and the
deployment has internet access.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError
from src.lib.yaml_parser import parse_yaml, get_nested


class AwsSnsReachability(BaseTarget):
    """Test connectivity to AWS SNS from inside the Gundeck pod.

    Uses the same check method documented for operators: curl to the SNS HTTPS
    endpoint. Any HTTP response (including 4xx) counts as reachable.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "AWS SNS reachability from Gundeck pod"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "When using real AWS for push notifications (Option A or B), gundeck "
            "must be able to reach the AWS SNS endpoint. If it can't, push "
            "notifications to mobile devices will fail."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test connectivity to AWS SNS from inside the Gundeck pod.

        Uses curl (matching Julia's documented check) from inside the Gundeck pod.
        Any HTTP response, including 4xx, confirms TCP+TLS connectivity.

        Returns:
            JSON string with reachability details.

        Raises:
            NotApplicableError: If fake-aws is in use or no internet.
        """
        if not self.config.options.has_internet:
            raise NotApplicableError("No internet access declared")

        self.terminal.step("Detecting push notification mode from gundeck config...")

        # Read gundeck config to get the region and detect if real AWS is in use
        try:
            _result, cm_data = self.run_kubectl("configmap/gundeck")
            if not isinstance(cm_data, dict):
                raise NotApplicableError("Cannot read gundeck ConfigMap")

            gundeck_yaml_str: str = cm_data.get("data", {}).get("gundeck.yaml", "")
            if not gundeck_yaml_str:
                raise NotApplicableError("gundeck ConfigMap missing gundeck.yaml")

            gundeck_config: dict[str, Any] = parse_yaml(gundeck_yaml_str)
            sns_endpoint: str = str(get_nested(gundeck_config, "aws.snsEndpoint", "") or "")
            region: str = str(get_nested(gundeck_config, "aws.region", "eu-west-1") or "eu-west-1")

        except (ValueError, RuntimeError) as e:
            raise NotApplicableError(f"Cannot determine push mode: {e}")

        if "fake-aws" in sns_endpoint.lower():
            raise NotApplicableError("Using fake-aws (Option C: websocket-only) — no real AWS to check")

        # Find a running gundeck pod to exec into
        target_host: str = f"sns.{region}.amazonaws.com"
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
                raise RuntimeError("No running gundeck pod found to exec into")

            # Use curl matching Julia's documented command:
            # curl -v --max-time 10 https://sns.<region>.amazonaws.com
            # Any HTTP response (even 4xx) confirms connectivity.
            namespace: str = self.config.cluster.kubernetes_namespace
            curl_cmd: str = (
                f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "
                f"https://{target_host}/"
            )
            exec_cmd: str = f"kubectl exec {gundeck_pod} -n {namespace} -- {curl_cmd}"

            cmd_result = self._run_shell_command(exec_cmd)
            if cmd_result and cmd_result.returncode == 0:
                # curl writes the HTTP status code to stdout via -w
                status_str: str = cmd_result.stdout.strip().strip("'\"")
                if status_str.isdigit():
                    http_status = int(status_str)
                    # Any HTTP response (including 4xx) confirms connectivity
                    reachable = http_status > 0
                else:
                    reachable = True
            elif cmd_result:
                # curl failed — might be a connection timeout or TLS error
                error_msg = cmd_result.stderr.strip() or "curl command failed"
                # Check if curl itself isn't available, fall back to wget
                if "not found" in error_msg.lower() or "executable" in error_msg.lower():
                    wget_cmd: str = (
                        f"wget -q -O /dev/null --timeout=10 --spider "
                        f"https://{target_host}/"
                    )
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
            self._health_info = f"AWS SNS reachable: {target_host}{status_info}"
        else:
            self._health_info = f"AWS SNS NOT reachable: {target_host} — {error_msg}"

        return json.dumps(result)
