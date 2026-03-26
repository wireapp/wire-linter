"""Detects pods stuck in Pending state and their scheduling failure reasons.

Pods that never start are different from unhealthy pods — they indicate
scheduling failures: not enough resources, unsatisfiable node affinity,
missing PVCs, taints without tolerations, etc.

The event messages from FailedScheduling events usually explain exactly
why scheduling failed, which makes this data actionable.

Produces a single data point at « kubernetes/pods/scheduling_failures ».
Value is a JSON string with pending pod details and scheduling events.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.per_service_target import WIRE_CORE_SERVICES
from src.lib.wire_service_helpers import filter_wire_service_pods


class SchedulingFailures(BaseTarget):
    """Finds pods stuck in Pending state and the events explaining why.

    Fetches all pods in the Wire namespace, filters for Pending phase,
    then fetches events to find FailedScheduling reasons.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Pods stuck in Pending state with scheduling failure events"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Pods stuck in Pending never started at all — usually because of "
            "insufficient resources, unresolvable node affinity, missing PVCs, "
            "or taints without tolerations. The FailedScheduling event messages "
            "explain exactly what went wrong."
        )

    def collect(self) -> str:
        """Fetch pending pods and their scheduling events.

        Returns:
            JSON string with pending pod details and scheduling event messages.
        """
        namespace: str = self.config.cluster.kubernetes_namespace

        self.terminal.step("Checking for pods stuck in Pending state...")

        # Fetch all pods in the namespace and filter for Pending
        _result, parsed = self.run_kubectl("pods", namespace=namespace)

        pending_pods: list[dict[str, Any]] = []

        if isinstance(parsed, dict):
            for pod in parsed.get("items", []):
                phase: str = pod.get("status", {}).get("phase", "")
                if phase == "Pending":
                    pod_name: str = pod.get("metadata", {}).get("name", "unknown")
                    pod_ns: str = pod.get("metadata", {}).get("namespace", namespace)

                    # Extract conditions for scheduling details
                    conditions: list[dict[str, str]] = []
                    for condition in pod.get("status", {}).get("conditions", []):
                        conditions.append({
                            "type": condition.get("type", ""),
                            "status": condition.get("status", ""),
                            "reason": condition.get("reason", ""),
                            "message": condition.get("message", ""),
                        })

                    pending_pods.append({
                        "name": pod_name,
                        "namespace": pod_ns,
                        "conditions": conditions,
                    })

        # Also check all-namespaces for Wire pods that may have ended up
        # in the wrong namespace — filter to Wire service names only so
        # unrelated system pods don't appear in the report
        if not pending_pods:
            _result_all, parsed_all = self.run_kubectl(
                "pods", all_namespaces=True
            )
            if isinstance(parsed_all, dict):
                # Filter to only pending pods first
                all_items: list[dict[str, Any]] = [
                    pod for pod in parsed_all.get("items", [])
                    if pod.get("status", {}).get("phase", "") == "Pending"
                ]

                # Filter to Wire service pods only to avoid false positives
                # on unrelated system pods with similar names
                wire_pending: list[dict[str, Any]] = filter_wire_service_pods(
                    all_items, WIRE_CORE_SERVICES
                )

                # Track seen pod names to prevent duplicates
                seen_names: set[str] = set()
                for pod in wire_pending:
                    pod_name = pod.get("metadata", {}).get("name", "unknown")
                    if pod_name in seen_names:
                        continue
                    seen_names.add(pod_name)
                    pod_ns = pod.get("metadata", {}).get("namespace", "")

                    conditions = []
                    for condition in pod.get("status", {}).get("conditions", []):
                        conditions.append({
                            "type": condition.get("type", ""),
                            "status": condition.get("status", ""),
                            "reason": condition.get("reason", ""),
                            "message": condition.get("message", ""),
                        })

                    pending_pods.append({
                        "name": pod_name,
                        "namespace": pod_ns,
                        "conditions": conditions,
                    })

        # Fetch events from every namespace where pending pods were found,
        # so that pods discovered via the all-namespaces fallback also get
        # their FailedScheduling events included in the output
        scheduling_events: list[dict[str, Any]] = []

        self.terminal.step("Fetching scheduling events...")

        # Collect unique namespaces from the pending pods — always include
        # the configured namespace so we still check for scheduling events
        # even when no pending pods were found yet (events may precede pods)
        event_namespaces: set[str] = {namespace}
        for pod in pending_pods:
            pod_ns_value: str = pod.get("namespace", "")
            if pod_ns_value:
                event_namespaces.add(pod_ns_value)

        for event_ns in sorted(event_namespaces):
            _result_events, events_parsed = self.run_kubectl(
                "events", namespace=event_ns
            )

            if isinstance(events_parsed, dict):
                for event in events_parsed.get("items", []):
                    reason: str = event.get("reason", "")
                    # Scheduling-related event reasons
                    if reason in (
                        "FailedScheduling", "FailedMount", "FailedAttachVolume",
                        "FailedBinding", "Unschedulable",
                    ):
                        involved: dict[str, str] = event.get("involvedObject", {})
                        scheduling_events.append({
                            "pod": involved.get("name", ""),
                            "namespace": event_ns,
                            "reason": reason,
                            "message": event.get("message", ""),
                            "count": event.get("count", 1),
                            "last_seen": event.get("lastTimestamp", ""),
                        })

        pending_count: int = len(pending_pods)

        if pending_count == 0:
            self._health_info = "No pods stuck in Pending state"
        else:
            names: str = ", ".join(p["name"] for p in pending_pods[:5])
            suffix: str = f" (+{pending_count - 5} more)" if pending_count > 5 else ""
            self._health_info = f"{pending_count} pending: {names}{suffix}"

        return json.dumps({
            "pending_count": pending_count,
            "pending_pods": pending_pods,
            "scheduling_events": scheduling_events[:50],
        }, sort_keys=True)
