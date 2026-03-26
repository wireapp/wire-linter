"""Display formatting helpers for terminal output.

Pure functions that format kubectl resources and CQL results into
human-readable terminal summaries. Extracted from base_target.py to
keep target lifecycle logic separate from display concerns.

Used by BaseTarget's run_kubectl() and run_cql_query() methods.
"""

from __future__ import annotations

from typing import Any

from src.lib.cql_types import CqlResult
from src.lib.kubectl import int_or_zero


def summarize_kubectl_item(item: dict[str, Any]) -> str:
    """Build a one-line summary of a single kubectl resource item.

    Pulls out the relevant fields depending on resource type. Pods get name/phase/restart
    count (if > 0), nodes get Ready/NotReady, PVCs get bound status, deployments/statefulsets/
    daemonsets show ready/desired replicas. Falls back to namespace/name and kind for others.

    Args:
        item: A single parsed kubectl JSON resource dict.

    Returns:
        A concise one-line summary string.
    """
    metadata: dict[str, Any] = item.get("metadata", {})
    name: str = metadata.get("name", "?")
    namespace: str = metadata.get("namespace", "")
    status: dict[str, Any] = item.get("status", {})
    spec: dict[str, Any] = item.get("spec", {})
    kind: str = item.get("kind", "")

    parts: list[str] = []

    # Identify by namespace/name when namespace is present
    if namespace:
        parts.append(f"{namespace}/{name}")
    else:
        parts.append(name)

    # Pod: show phase and restarts
    phase: str = status.get("phase", "")
    container_statuses: list[dict[str, Any]] = status.get("containerStatuses", [])
    if phase and (container_statuses or kind == "Pod"):
        parts.append(phase)
        if container_statuses:
            restarts: int = sum(
                cs.get("restartCount", 0) for cs in container_statuses
            )
            if restarts > 0:
                parts.append(f"restarts={restarts}")
        return "  ".join(parts)

    # Node: show Ready condition
    conditions: list[dict[str, Any]] = status.get("conditions", [])
    for condition in conditions:
        if condition.get("type") == "Ready":
            ready_str: str = (
                "Ready" if condition.get("status") == "True" else "NotReady"
            )
            parts.append(ready_str)
            return "  ".join(parts)

    # Deployment/StatefulSet/DaemonSet: show replica counts
    if "replicas" in status:
        desired: int = int_or_zero(status, "replicas")
        ready: int = int_or_zero(status, "readyReplicas")
        parts.append(f"{ready}/{desired} ready")
        return "  ".join(parts)

    # PVC: show bound phase
    if "accessModes" in spec or kind == "PersistentVolumeClaim":
        pvc_phase: str = status.get("phase", "")
        if pvc_phase:
            parts.append(pvc_phase)
        return "  ".join(parts)

    # Ingress: show hosts
    if "rules" in spec or kind == "Ingress":
        hosts: list[str] = [
            rule.get("host", "")
            for rule in spec.get("rules", [])
            if rule.get("host")
        ]
        if hosts:
            parts.append(", ".join(hosts))
        return "  ".join(parts)

    # Secret/ConfigMap: show data key count
    data_field: dict[str, Any] | None = item.get("data")
    if data_field is not None and isinstance(data_field, dict):
        parts.append(f"{len(data_field)} keys")
        return "  ".join(parts)

    # Generic fallback
    if kind:
        parts.append(f"({kind})")

    return "  ".join(parts)


def format_cql_result(result: CqlResult) -> str:
    """Format a CqlResult as readable text for terminal display.

    One line per row, column values separated by « | ». Maps and collections
    shown as compact key=value notation.

    Args:
        result: The CqlResult to format.

    Returns:
        A multi-line string, one line per row.
    """
    if not result.rows:
        return "(no rows)"

    names: list[str] = result.column_names
    lines: list[str] = []

    for row in result.rows:
        parts: list[str] = []
        for col_idx, value in enumerate(row):
            col_name: str = names[col_idx] if col_idx < len(names) else f"col{col_idx}"

            if isinstance(value, dict):
                # Compact map display: key=val, key=val
                map_parts: list[str] = [
                    f"{k}={v}" for k, v in value.items()
                ]
                formatted: str = ", ".join(map_parts)
                parts.append(f"{col_name}: {{{formatted}}}")
            elif isinstance(value, list):
                parts.append(f"{col_name}: [{', '.join(str(v) for v in value)}]")
            else:
                parts.append(f"{col_name}: {value}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)
