"""Shared helper for finding RabbitMQ pods via kubectl.

All direct/rabbitmq targets need to locate a RabbitMQ pod before they can
run rabbitmqctl commands inside it. This module centralises that logic so
label selectors and namespace handling live in one place.

Wire deploys RabbitMQ as a separate Helm chart (wire/rabbitmq), which may
land in a different namespace than the main wire-server chart. We search
across all namespaces to handle that.
"""

from __future__ import annotations

# External
from typing import Any, TYPE_CHECKING

# Ours
from src.lib.base_target import NotApplicableError

if TYPE_CHECKING:
    # Avoid circular import at runtime — only needed for type checking
    from src.lib.base_target import BaseTarget


def _has_rabbitmq_container(pod: dict[str, Any]) -> bool:
    """Check whether a pod spec includes a container named 'rabbitmq'.

    The actual RabbitMQ broker pod always has a container called 'rabbitmq',
    while sidecar pods (exporters, operators) use different container names.
    This lets Strategy 3's name-based search reject non-broker pods.
    """
    containers: list[dict[str, Any]] = (
        pod.get("spec", {}).get("containers", [])
    )
    return any(c.get("name") == "rabbitmq" for c in containers)


def find_rabbitmq_pod(target: BaseTarget) -> tuple[str, str]:
    """Find a running RabbitMQ pod name and namespace.

    Searches across ALL namespaces because RabbitMQ is installed as a
    separate Helm chart and may not be in the same namespace as wire-server.

    Tries three strategies in order:
    1. Standard Kubernetes label (app.kubernetes.io/name=rabbitmq)
    2. Legacy app=rabbitmq label
    3. Name-based search for pods with "rabbitmq" in name AND a container named "rabbitmq"

    Args:
        target: The BaseTarget instance (provides run_kubectl).

    Returns:
        Tuple of (pod_name, namespace).

    Raises:
        NotApplicableError: If no RabbitMQ pods are found in any namespace.
            This signals that RabbitMQ likely runs on VMs, not in Kubernetes.
    """
    # Strategy 1: standard Kubernetes label across all namespaces
    _cmd_result, data = target.run_kubectl(
        "pods",
        selector="app.kubernetes.io/name=rabbitmq",
        all_namespaces=True,
    )

    # Strategy 2: simpler legacy label
    if data is None or not data.get("items"):
        _cmd_result, data = target.run_kubectl(
            "pods",
            selector="app=rabbitmq",
            all_namespaces=True,
        )

    # Strategy 3: name-based search across all namespaces
    if data is None or not data.get("items"):
        _cmd_result_all, data_all = target.run_kubectl(
            "pods",
            all_namespaces=True,
        )
        if data_all:
            rabbitmq_pods: list[dict[str, Any]] = [
                p for p in data_all.get("items", [])
                if "rabbitmq" in p.get("metadata", {}).get("name", "").lower()
                and _has_rabbitmq_container(p)
            ]
            if rabbitmq_pods:
                data = {"items": rabbitmq_pods}

    if data is None or not data.get("items"):
        # In production Wire deployments RabbitMQ runs on VMs (datanodes),
        # not as k8s pods. This isn't an error — the SSH-based targets
        # in databases/rabbitmq/ handle that case. Signal not_applicable
        # so the summary doesn't show a scary collection failure.
        raise NotApplicableError(
            "No RabbitMQ pods found in any namespace. "
            "RabbitMQ likely runs on VMs, not in Kubernetes."
        )

    # Sort so Running pods come first — avoids picking a pod in
    # CrashLoopBackOff / Pending / Failed which would cause kubectl exec failures
    items: list[dict[str, Any]] = data["items"]
    items.sort(key=lambda p: 0 if p.get("status", {}).get("phase") == "Running" else 1)

    # Only exec into Running pods — if none exist, give a clear diagnostic
    # message rather than letting kubectl exec fail with a cryptic container error
    running: list[dict[str, Any]] = [
        p for p in items if p.get("status", {}).get("phase") == "Running"
    ]
    if not running:
        raise NotApplicableError(
            f"Found {len(items)} RabbitMQ pod(s) but none are Running. "
            "Pods may be in CrashLoopBackOff, Pending, or Failed state."
        )

    pod_name: str = running[0]["metadata"]["name"]
    namespace: str = running[0]["metadata"].get("namespace", "default")

    return pod_name, namespace
