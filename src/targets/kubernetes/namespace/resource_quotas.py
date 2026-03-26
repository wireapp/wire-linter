"""Fetches ResourceQuota usage from the Wire namespace.

Without quotas, one runaway deployment can consume all cluster resources.
With quotas, operators need to monitor usage vs limits to avoid rejections
when deploying or scaling.

Produces a single data point at « kubernetes/namespace/resource_quotas ».
Value is a JSON string with quota details and usage.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class ResourceQuotas(BaseTarget):
    """Fetches ResourceQuota definitions and current usage.

    Reports what quotas exist in the Wire namespace and how close
    usage is to the hard limits.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Namespace resource quotas and usage"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "ResourceQuotas limit how much CPU, memory, and other resources a "
            "namespace can consume. Without them, a single runaway deployment "
            "can eat all cluster resources. When quotas exist, monitoring usage "
            "vs limits prevents deployment failures from quota exhaustion."
        )

    def collect(self) -> str:
        """Fetch ResourceQuotas from the Wire namespace.

        Returns:
            JSON string with quota count, limits, and current usage.
        """
        namespace: str = self.config.cluster.kubernetes_namespace

        self.terminal.step("Fetching namespace resource quotas...")

        _result, parsed = self.run_kubectl(
            "resourcequotas", namespace=namespace
        )

        quotas: list[dict[str, Any]] = []

        if isinstance(parsed, dict):
            for item in parsed.get("items", []):
                quota_status: dict[str, Any] = item.get("status", {})
                hard: dict[str, str] = quota_status.get("hard", {})
                used: dict[str, str] = quota_status.get("used", {})

                quotas.append({
                    "name": item.get("metadata", {}).get("name", ""),
                    "hard": hard,
                    "used": used,
                })

        quota_count: int = len(quotas)

        if quota_count == 0:
            self._health_info = "No resource quotas configured"
        else:
            self._health_info = f"{quota_count} resource quota(s) found"

        return json.dumps({
            "quota_count": quota_count,
            "quotas": quotas,
        }, sort_keys=True)
