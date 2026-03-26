"""Fetches recent Kubernetes warning events from the Wire namespace.

Warning events surface image pull failures, OOMKilled containers,
FailedScheduling, FailedMount, liveness probe failures, and other
problems that don't always show up in pod status alone.

Produces a single data point at « kubernetes/events/warnings ».
Value is a JSON string with warning event summary and details.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Maximum number of individual events to include in the data point
_MAX_EVENTS: int = 50


class WarningEvents(BaseTarget):
    """Fetches recent warning events from the Wire namespace.

    Queries all events in the namespace, filters for type=Warning,
    and summarizes the top reasons and recent examples.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Recent Kubernetes warning events"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Kubernetes warning events surface problems like image pull failures, "
            "OOMKilled containers, FailedScheduling, probe failures, and mount "
            "errors. These often explain why things are broken when pod status "
            "alone looks fine."
        )

    def collect(self) -> str:
        """Fetch warning events from the Wire namespace.

        Returns:
            JSON string with warning count, top reasons, and recent events.
        """
        namespace: str = self.config.cluster.kubernetes_namespace

        self.terminal.step("Fetching warning events...")

        _result, parsed = self.run_kubectl("events", namespace=namespace)

        warnings: list[dict[str, Any]] = []
        reason_counts: dict[str, int] = {}

        if isinstance(parsed, dict):
            for event in parsed.get("items", []):
                event_type: str = event.get("type", "")
                if event_type != "Warning":
                    continue

                reason: str = event.get("reason", "unknown")
                involved: dict[str, str] = event.get("involvedObject", {})

                # In k8s 1.25+ (events.k8s.io/v1) firstTimestamp/lastTimestamp
                # are deprecated and often empty. Fall back to eventTime and
                # series.lastObservedTime which replaced them. Repeated-event
                # tracking also moved from top-level count to series.count.
                series: dict[str, Any] = event.get("series", {}) or {}

                # Prefer series.count (k8s 1.25+) over top-level count (deprecated),
                # defaulting to 1 when neither is present (single-occurrence event).
                count: int = (series.get("count") or event.get("count")) or 1

                # Track reason frequency
                reason_counts[reason] = reason_counts.get(reason, 0) + count
                first_seen: str = (
                    event.get("firstTimestamp", "")
                    or event.get("eventTime", "")
                    or series.get("lastObservedTime", "")
                    or ""
                )
                last_seen: str = (
                    event.get("lastTimestamp", "")
                    or series.get("lastObservedTime", "")
                    or event.get("eventTime", "")
                    or ""
                )

                warnings.append({
                    "reason": reason,
                    "message": event.get("message", ""),
                    "object_kind": involved.get("kind", ""),
                    "object_name": involved.get("name", ""),
                    "count": count,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                })

        # Sort by last_seen descending, take most recent.
        # Use '0000' as a sentinel for empty timestamps. Both '' and '0000'
        # sort before any ISO timestamp lexicographically, so with reverse=True
        # both would place timestamp-less events last. '0000' is used here
        # purely for readability — it makes the intent (a low-value sentinel)
        # clearer than an empty string at a glance.
        warnings.sort(
            key=lambda e: (e.get("last_seen") or "0000", e.get("first_seen") or "0000"),
            reverse=True,
        )
        recent_warnings: list[dict[str, Any]] = warnings[:_MAX_EVENTS]

        # Sort reasons by frequency descending
        top_reasons: dict[str, int] = dict(
            sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
        )

        total: int = len(warnings)

        # Sum all occurrence counts across every event record to get the true
        # total number of times warnings fired (vs. the number of distinct records).
        total_occurrences: int = sum(w["count"] for w in warnings)

        if total == 0:
            self._health_info = "No warning events"
        else:
            top_3: str = ", ".join(
                f"{reason}({count})" for reason, count in list(top_reasons.items())[:3]
            )
            # Report both: distinct event records and total occurrence count so
            # readers can distinguish "1 record seen 47 times" from "47 separate records".
            self._health_info = f"{total} warning event(s) ({total_occurrences} occurrence(s)): {top_3}"

        return json.dumps({
            "total_warning_count": total,
            "total_occurrence_count": total_occurrences,
            "recent_warnings": recent_warnings,
            "top_reasons": top_reasons,
        }, sort_keys=True)
