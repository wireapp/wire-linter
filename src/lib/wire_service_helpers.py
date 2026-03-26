"""Shared helpers for Wire service targets.

Provides functions to query service pod status and count replicas via kubectl.
Used by all wire_services/ target files to avoid duplicating kubectl pod
querying logic individual service targets remain thin wrappers.

Classes:
    PodCache: Thread-safe TTL cache for expensive all-namespaces pod queries.

Functions:
    get_service_pods: Query pods for a Wire service by label or name prefix.
    filter_wire_service_pods: Filter a pod list to only Wire service pods.
    is_service_healthy: Check if all pods are Running with all containers ready.
    count_replicas: Count running replicas for a service.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from typing import Any, Callable

from src.lib.command import CommandResult
from src.lib.logger import Logger


class PodCache:
    """Thread-safe TTL cache for the all-namespaces pod query.

    In large clusters (1000+ pods), fetching every pod via kubectl takes 5-10
    seconds. With 20+ service health targets that each need the full pod list,
    caching saves ~200 seconds per run.

    Two TTLs handle the common cases:
      - Non-empty results expire after a longer TTL (120s by default) so pod
        changes (crashes, restarts) are eventually picked up during long runs.
      - Empty results expire after a shorter TTL (5s) so the caller retries
        sooner in case kubectl was transiently failing.

    Thread-safe: multiple worker threads in parallel mode share one cache.
    """

    def __init__(
        self,
        empty_ttl: float = 5.0,
        nonempty_ttl: float = 120.0,
    ) -> None:
        self._entry: tuple[CommandResult, list[dict[str, Any]], float] | None = None
        self._lock: threading.Lock = threading.Lock()
        self._empty_ttl: float = empty_ttl
        self._nonempty_ttl: float = nonempty_ttl

    def clear(self) -> None:
        """Reset the cache. Called between runs and in tests."""
        with self._lock:
            self._entry = None

    def _is_stale(
        self,
        entry: tuple[CommandResult, list[dict[str, Any]], float] | None,
    ) -> bool:
        """Return True if the cache entry is missing or expired."""
        if entry is None:
            return True
        _, pods, timestamp = entry
        age: float = time.monotonic() - timestamp
        if len(pods) > 0:
            return age >= self._nonempty_ttl
        return age >= self._empty_ttl

    def get_or_fetch(
        self,
        kubectl_fn: Callable,
    ) -> tuple[CommandResult, list[dict[str, Any]]]:
        """Return cached pods or fetch fresh ones via kubectl.

        Uses double-checked locking: fast path reads without the lock,
        slow path acquires the lock and re-checks before fetching.

        Args:
            kubectl_fn: The target's run_kubectl method.

        Returns:
            Tuple of (CommandResult for raw_output, list of all pod dicts).
        """
        # Fast path: cache is fresh, no lock needed
        snapshot: tuple[CommandResult, list[dict[str, Any]], float] | None = self._entry
        if not self._is_stale(snapshot):
            cmd_result, pods, _ = snapshot  # type: ignore[misc]
            return (cmd_result, pods)

        # Slow path: acquire lock, re-check, fetch if still stale
        with self._lock:
            snapshot = self._entry
            if not self._is_stale(snapshot):
                cmd_result, pods, _ = snapshot  # type: ignore[misc]
                return (cmd_result, pods)

            # Fetch all pods across all namespaces
            cmd_result_fresh, parsed = kubectl_fn("pods", all_namespaces=True)
            pods_fresh: list[dict[str, Any]] = (
                parsed.get("items", []) if isinstance(parsed, dict) else []
            )

            # Cache the result (including empty results with short TTL)
            self._entry = (cmd_result_fresh, pods_fresh, time.monotonic())
            return (cmd_result_fresh, pods_fresh)


# Module-level singleton used by get_service_pods(). Tests call
# clear_pod_cache() which delegates to _pod_cache.clear().
_pod_cache: PodCache = PodCache()


def clear_pod_cache() -> None:
    """Reset the all-namespaces pod cache between runs or for testing."""
    _pod_cache.clear()


def get_service_pods(
    service_name: str,
    kubectl_fn: Callable,
    namespace: str,
    logger: Logger | None = None,
) -> tuple[CommandResult, list[dict[str, Any]]]:
    """Find pods for a Wire service using label or name prefix.

    Tries the app= label first, then falls back to searching all pods by
    name prefix. If nothing is found in the configured namespace, searches
    all namespaces as a safety net in case the namespace is misconfigured.

    Args:
        service_name: The Wire service name (e.g., 'brig', 'galley').
        kubectl_fn: The target's run_kubectl method.
        namespace: Kubernetes namespace to search in.
        logger: Logger instance for emitting warnings; uses print() fallback if omitted.

    Returns:
        Tuple of (CommandResult for raw_output, list of matching pod dicts).
    """
    # Try the app= label first, since most deployments use it
    cmd_result, parsed = kubectl_fn("pods", namespace=namespace, selector=f"app={service_name}")
    pods: list[dict[str, Any]] = parsed.get("items", []) if isinstance(parsed, dict) else []

    if len(pods) > 0:
        return (cmd_result, pods)

    # If label selector fails, list all pods and filter by name prefix
    cmd_result_all, parsed_all = kubectl_fn("pods", namespace=namespace)
    all_pods: list[dict[str, Any]] = parsed_all.get("items", []) if isinstance(parsed_all, dict) else []
    filtered: list[dict[str, Any]] = _filter_pods_by_name(all_pods, service_name)

    if len(filtered) > 0:
        return (cmd_result_all, filtered)

    # If nothing found, try searching all namespaces with the label
    # (the namespace might be misconfigured)
    cmd_result_global, parsed_global = kubectl_fn("pods", all_namespaces=True, selector=f"app={service_name}")
    global_pods: list[dict[str, Any]] = (
        parsed_global.get("items", []) if isinstance(parsed_global, dict) else []
    )

    if len(global_pods) > 0:
        # Warn if pods were found in a namespace other than the configured one
        _warn_namespace_mismatch(global_pods, namespace, service_name, logger)
        return (cmd_result_global, global_pods)

    # Last resort: all namespaces with name prefix matching, using the
    # PodCache so this expensive query runs at most once per execution.
    cached_cmd_result, cached_pods = _pod_cache.get_or_fetch(kubectl_fn)
    filtered_global: list[dict[str, Any]] = _filter_pods_by_name(cached_pods, service_name)

    # Warn if pods were found in a namespace other than the configured one
    if len(filtered_global) > 0:
        _warn_namespace_mismatch(filtered_global, namespace, service_name, logger)

    return (cached_cmd_result, filtered_global)


def _matches_deployment_pod_name(pod_name: str, service_name: str) -> bool:
    """Check if a pod name matches Kubernetes deployment/statefulset naming.

    Deployment pods follow {name}-{rs-hash}-{pod-hash} where both hash
    segments use only the Kubernetes SafeEncodeString charset: consonants
    bcdfghjklmnpqrstvwxz plus digits 2-9 (no vowels, no 0 or 1).

    StatefulSet pods follow {name}-{ordinal} where ordinal is a
    non-negative decimal integer (e.g. cassandra-0, elasticsearch-1).

    By requiring exactly two hash-like segments for Deployments, we avoid
    false positives from job/migration pods that may have consonant-only
    words (e.g. ntp, sync, dns, tls) in their names.
    """
    # Kubernetes SafeEncodeString charset — consonants + digits 2-9
    hash_charset: str = r'[bcdfghjklmnpqrstvwxz2-9]'

    escaped_name: str = re.escape(service_name)

    # Deployment: {service}-{replicaset-hash}-{pod-hash}
    deployment_pattern: str = rf'^{escaped_name}-{hash_charset}+-{hash_charset}+$'

    # StatefulSet: {service}-{ordinal} where ordinal is a non-negative integer
    statefulset_pattern: str = rf'^{escaped_name}-\d+$'

    return (
        re.match(deployment_pattern, pod_name) is not None
        or re.match(statefulset_pattern, pod_name) is not None
    )


def _filter_pods_by_name(
    pods: list[dict[str, Any]],
    service_name: str,
) -> list[dict[str, Any]]:
    """Return pods whose names match the deployment naming convention for the service."""
    return [
        pod for pod in pods
        if _matches_deployment_pod_name(
            pod.get("metadata", {}).get("name", ""),
            service_name,
        )
    ]


def _warn_namespace_mismatch(
    pods: list[dict[str, Any]],
    expected_namespace: str,
    service_name: str,
    logger: Logger | None = None,
) -> None:
    """Log a warning to stderr if any pods are in a namespace other than expected.

    This helps operators detect namespace misconfigurations — e.g. pods
    deployed to 'default' when the config says 'wire'.

    Args:
        pods: Pod dicts to inspect for namespace metadata.
        expected_namespace: The namespace the service is configured to use.
        service_name: Service name used in the warning message.
        logger: Logger instance for consistent formatted output; falls back to
                print() when not provided (e.g. in unit tests that omit it).
    """
    unexpected_namespaces: set[str] = set()
    for pod in pods:
        pod_ns: str = pod.get("metadata", {}).get("namespace", "")
        if pod_ns != expected_namespace:
            unexpected_namespaces.add(pod_ns)

    if unexpected_namespaces:
        ns_list: str = ", ".join(sorted(unexpected_namespaces))
        message: str = (
            f"{service_name}: pods found in namespace(s) "
            f"{ns_list} instead of expected namespace {expected_namespace} "
            f"— the namespace may be misconfigured"
        )
        if logger is not None:
            logger.warning(message)
        else:
            print(f"[WARNING] {message}", file=sys.stderr, flush=True)


def filter_wire_service_pods(
    pods: list[dict[str, Any]],
    services: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Filter pods to only those belonging to the given Wire services.

    Matches pods whose metadata.name starts with any service name from
    the provided specs. Used to separate Wire pods from unrelated system
    pods when scanning all namespaces.

    Args:
        pods: List of Kubernetes pod dicts (from kubectl JSON output).
        services: List of ServiceSpec dicts, each with at least a 'name' key.

    Returns:
        Subset of pods matching any service name prefix.
    """
    service_names: list[str] = [s["name"] for s in services]
    return [
        pod for pod in pods
        if any(
            _matches_deployment_pod_name(
                pod.get("metadata", {}).get("name", ""),
                name,
            )
            for name in service_names
        )
    ]


def is_service_healthy(pods: list[dict[str, Any]]) -> bool:
    """Check if all pods are Running with all containers ready."""
    if not pods:
        return False

    for pod in pods:
        phase: str = pod.get("status", {}).get("phase", "")
        if phase != "Running":
            return False

        container_statuses: list[dict[str, Any]] = pod.get("status", {}).get("containerStatuses", [])
        if not container_statuses:
            return False

        if not all(cs.get("ready", False) for cs in container_statuses):
            return False

    return True


def count_replicas(pods: list[dict[str, Any]]) -> int:
    """Count how many pods are in Running phase."""
    return sum(1 for pod in pods if pod.get("status", {}).get("phase") == "Running")


def replica_label(count: int) -> str:
    """Return '{count} replica(s) running' with correct singular/plural."""
    noun: str = "replica" if count == 1 else "replicas"
    return f"{count} {noun} running"
