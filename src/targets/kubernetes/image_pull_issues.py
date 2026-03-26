"""Detects pods stuck in ImagePullBackOff or ErrImagePull state.

Julia described the failure mode: in Wire-managed offline clusters without an
image registry, containerd may garbage-collect images when disk runs low. When
a pod is then rescheduled to that node, it can't pull the image and gets stuck.

This target catches the actual failure by checking pod statuses. A more thorough
check (SSH to each node, list images, compare across nodes) is in
kubernetes/node_image_inventory.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class ImagePullIssues(BaseTarget):
    """Detect pods stuck in ImagePullBackOff or ErrImagePull state.

    Scans all pods in the Wire namespace for container status conditions
    indicating image pull failures.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Pods with image pull failures (ImagePullBackOff / ErrImagePull)"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "In offline deployments without a container image registry, containerd "
            "may evict images from local storage when disk space runs low. If a pod "
            "is then scheduled on a node missing its image, it enters "
            "ImagePullBackOff — the pod is stuck and the service is down."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check all pods for image pull failures.

        Returns:
            JSON string with affected pod details.
        """
        self.terminal.step("Scanning pods for image pull failures...")

        _result, data = self.run_kubectl("pods")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch pod list")

        items: list[dict[str, Any]] = data.get("items", [])
        affected_pods: list[dict[str, str]] = []

        for pod in items:
            pod_name: str = pod.get("metadata", {}).get("name", "")
            # Check init container statuses and regular container statuses
            all_statuses: list[dict[str, Any]] = (
                pod.get("status", {}).get("containerStatuses", [])
                + pod.get("status", {}).get("initContainerStatuses", [])
            )

            for container_status in all_statuses:
                waiting: dict[str, Any] = container_status.get("state", {}).get("waiting", {})
                reason: str = waiting.get("reason", "")

                # These are the two image-pull-failure states
                if reason in ("ImagePullBackOff", "ErrImagePull"):
                    image: str = container_status.get("image", "unknown")
                    message: str = waiting.get("message", "")
                    affected_pods.append({
                        "pod": pod_name,
                        "image": image,
                        "reason": reason,
                        "message": message,
                    })

        total_affected: int = len(affected_pods)

        result: dict[str, Any] = {
            "affected_pods": affected_pods,
            "total_affected": total_affected,
        }

        if total_affected == 0:
            self._health_info = "No pods have image pull issues"
        else:
            pod_names: str = ", ".join(p["pod"] for p in affected_pods[:5])
            suffix: str = f" (and {total_affected - 5} more)" if total_affected > 5 else ""
            self._health_info = f"{total_affected} pod(s) with image pull issues: {pod_names}{suffix}"

        return json.dumps(result)
