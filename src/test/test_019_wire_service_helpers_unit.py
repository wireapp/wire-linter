"""Tests for wire service helpers (src/lib/wire_service_helpers.py).

Tests get_service_pods, is_service_healthy, and count_replicas. We mock out kubectl
to simulate what the API actually returns.
"""

from __future__ import annotations

from typing import Any

from src.lib.command import CommandResult
from src.lib.wire_service_helpers import PodCache, clear_pod_cache, count_replicas, get_service_pods, is_service_healthy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cmd_result(stdout: str = "", command: str = "kubectl") -> CommandResult:
    """Construct a successful CommandResult with the given stdout."""
    return CommandResult(
        command=command,
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.01,
        success=True,
        timed_out=False,
    )


def _make_pod(name: str, phase: str = "Running", ready: bool = True) -> dict[str, Any]:
    """Create a minimal pod dict that looks like kubectl JSON output."""
    return {
        "metadata": {"name": name},
        "status": {
            "phase": phase,
            "containerStatuses": [{"ready": ready}],
        },
    }


def _make_pod_multi_container(
    name: str,
    phase: str = "Running",
    container_readiness: list[bool] | None = None,
) -> dict[str, Any]:
    """Create a pod dict with multiple containers in it."""
    if container_readiness is None:
        container_readiness = [True]
    return {
        "metadata": {"name": name},
        "status": {
            "phase": phase,
            "containerStatuses": [{"ready": r} for r in container_readiness],
        },
    }


# ===========================================================================
# get_service_pods: label selector succeeds
# ===========================================================================

def test_get_service_pods_label_match() -> None:
    """get_service_pods returns pods when the label selector actually finds them."""
    clear_pod_cache()
    expected_result: CommandResult = _cmd_result()
    expected_pods: list[dict[str, Any]] = [_make_pod("brig-abc123")]

    def mock_kubectl(resource: str, namespace: str | None = None, selector: str | None = None, all_namespaces: bool = False) -> tuple[CommandResult, dict[str, Any]]:
        """Only returns pods if the right label selector is passed in."""
        if selector == "app=brig":
            return (expected_result, {"items": expected_pods})
        return (expected_result, {"items": []})

    cmd_result, pods = get_service_pods("brig", mock_kubectl, "wire")
    assert len(pods) == 1
    assert pods[0]["metadata"]["name"] == "brig-abc123"


def test_get_service_pods_label_multiple() -> None:
    """get_service_pods should return all the pods that match the label."""
    clear_pod_cache()
    pods_data: list[dict[str, Any]] = [
        _make_pod("brig-abc"),
        _make_pod("brig-def"),
        _make_pod("brig-ghi"),
    ]

    def mock_kubectl(resource: str, namespace: str | None = None, selector: str | None = None, all_namespaces: bool = False) -> tuple[CommandResult, dict[str, Any]]:
        if selector == "app=brig":
            return (_cmd_result(), {"items": pods_data})
        return (_cmd_result(), {"items": []})

    cmd_result, pods = get_service_pods("brig", mock_kubectl, "wire")
    assert len(pods) == 3


# ===========================================================================
# get_service_pods: fallback to name prefix
# ===========================================================================

def test_get_service_pods_fallback_to_name_prefix() -> None:
    """When the label selector fails, get_service_pods falls back to filtering by name prefix."""
    clear_pod_cache()
    all_pods: list[dict[str, Any]] = [
        _make_pod("brig-7bc2df-x5k3m"),
        _make_pod("brig-df8gk4-z9p2n"),
        _make_pod("galley-xyz789"),
    ]

    def mock_kubectl(resource: str, namespace: str | None = None, selector: str | None = None, all_namespaces: bool = False) -> tuple[CommandResult, dict[str, Any]]:
        # Label selector returns nothing; that forces the fallback
        if selector is not None:
            return (_cmd_result(), {"items": []})
        # Unfiltered query gives us all pods
        return (_cmd_result(), {"items": all_pods})

    cmd_result, pods = get_service_pods("brig", mock_kubectl, "wire")
    # After name-prefix filtering, we should only get the brig pods
    assert len(pods) == 2
    assert all(p["metadata"]["name"].startswith("brig") for p in pods)


def test_get_service_pods_fallback_no_matches() -> None:
    """If nothing matches by label or by name prefix, we get an empty list."""
    clear_pod_cache()
    all_pods: list[dict[str, Any]] = [_make_pod("galley-abc")]

    def mock_kubectl(resource: str, namespace: str | None = None, selector: str | None = None, all_namespaces: bool = False) -> tuple[CommandResult, dict[str, Any]]:
        if selector is not None:
            return (_cmd_result(), {"items": []})
        return (_cmd_result(), {"items": all_pods})

    cmd_result, pods = get_service_pods("brig", mock_kubectl, "wire")
    assert len(pods) == 0


def test_get_service_pods_none_parsed() -> None:
    """What happens if the kubectl response is None? Should handle it without crashing."""
    clear_pod_cache()
    def mock_kubectl(resource: str, namespace: str | None = None, selector: str | None = None, all_namespaces: bool = False) -> tuple[CommandResult, Any]:
        # Simulate kubectl returning None (parse failed)
        return (_cmd_result(), None)

    cmd_result, pods = get_service_pods("brig", mock_kubectl, "wire")
    assert len(pods) == 0


def test_get_service_pods_passes_namespace() -> None:
    """get_service_pods should pass the namespace through to the kubectl function."""
    clear_pod_cache()
    received_namespaces: list[str | None] = []

    def mock_kubectl(resource: str, namespace: str | None = None, selector: str | None = None, all_namespaces: bool = False) -> tuple[CommandResult, dict[str, Any]]:
        received_namespaces.append(namespace)
        if selector is not None:
            return (_cmd_result(), {"items": [_make_pod("brig-abc")]})
        return (_cmd_result(), {"items": []})

    get_service_pods("brig", mock_kubectl, namespace="custom-ns")
    assert received_namespaces[0] == "custom-ns"


def test_get_service_pods_all_ns_cache() -> None:
    """The all-namespaces fallback query should only run once across multiple calls."""
    clear_pod_cache()
    all_ns_call_count: int = 0

    def mock_kubectl(
        resource: str,
        namespace: str | None = None,
        selector: str | None = None,
        all_namespaces: bool = False,
    ) -> tuple[CommandResult, dict[str, Any]]:
        nonlocal all_ns_call_count
        # Track how many times the unfiltered all-namespaces call happens
        if all_namespaces and selector is None:
            all_ns_call_count += 1
        # Everything returns empty so every call cascades to the last fallback
        if selector is not None:
            return (_cmd_result(), {"items": []})
        if all_namespaces:
            # Include namespace metadata so the namespace filter matches
            brig_pod: dict[str, Any] = _make_pod("brig-7bcd5f-k3m2n")
            brig_pod["metadata"]["namespace"] = "wire"
            galley_pod: dict[str, Any] = _make_pod("galley-9fghk2-p4r7s")
            galley_pod["metadata"]["namespace"] = "wire"
            return (_cmd_result(), {"items": [brig_pod, galley_pod]})
        return (_cmd_result(), {"items": []})

    # First call: should fetch all-namespaces pods and cache them
    _, pods_brig = get_service_pods("brig", mock_kubectl, "wire")
    assert len(pods_brig) == 1
    assert pods_brig[0]["metadata"]["name"] == "brig-7bcd5f-k3m2n"
    assert all_ns_call_count == 1

    # Second call for a different service: should reuse the cache
    _, pods_galley = get_service_pods("galley", mock_kubectl, "wire")
    assert len(pods_galley) == 1
    assert pods_galley[0]["metadata"]["name"] == "galley-9fghk2-p4r7s"
    # The all-namespaces query should NOT have run again
    assert all_ns_call_count == 1


# ===========================================================================
# is_service_healthy
# ===========================================================================

def test_is_service_healthy_all_running_ready() -> None:
    """When all pods are Running and all containers are Ready, we return True."""
    pods: list[dict[str, Any]] = [
        _make_pod("brig-abc", phase="Running", ready=True),
        _make_pod("brig-def", phase="Running", ready=True),
    ]
    assert is_service_healthy(pods) is True


def test_is_service_healthy_empty_list() -> None:
    """No pods means unhealthy; return False."""
    assert is_service_healthy([]) is False


def test_is_service_healthy_one_not_running() -> None:
    """If even one pod isn't Running, the whole thing's unhealthy."""
    pods: list[dict[str, Any]] = [
        _make_pod("brig-abc", phase="Running", ready=True),
        _make_pod("brig-def", phase="Pending", ready=True),
    ]
    assert is_service_healthy(pods) is False


def test_is_service_healthy_container_not_ready() -> None:
    """A pod that's Running but has an unready container? That's still unhealthy."""
    pods: list[dict[str, Any]] = [
        _make_pod("brig-abc", phase="Running", ready=False),
    ]
    assert is_service_healthy(pods) is False


def test_is_service_healthy_missing_container_statuses() -> None:
    """No containerStatuses field? Treat it as unhealthy."""
    pods: list[dict[str, Any]] = [{
        "metadata": {"name": "brig-abc"},
        "status": {"phase": "Running"},
    }]
    assert is_service_healthy(pods) is False


def test_is_service_healthy_empty_container_statuses() -> None:
    """Empty containerStatuses list means the pod isn't ready."""
    pods: list[dict[str, Any]] = [{
        "metadata": {"name": "brig-abc"},
        "status": {"phase": "Running", "containerStatuses": []},
    }]
    assert is_service_healthy(pods) is False


def test_is_service_healthy_multi_container_all_ready() -> None:
    """Multi-container pods should work fine; check all containers are ready."""
    pods: list[dict[str, Any]] = [
        _make_pod_multi_container("brig-abc", "Running", [True, True, True]),
    ]
    assert is_service_healthy(pods) is True


def test_is_service_healthy_multi_container_one_not_ready() -> None:
    """One unready container in a multi-container pod should fail the check."""
    pods: list[dict[str, Any]] = [
        _make_pod_multi_container("brig-abc", "Running", [True, False, True]),
    ]
    assert is_service_healthy(pods) is False


def test_is_service_healthy_single_pod() -> None:
    """Single running pod with ready container should be healthy."""
    pods: list[dict[str, Any]] = [_make_pod("sftd-abc", phase="Running", ready=True)]
    assert is_service_healthy(pods) is True


# ===========================================================================
# count_replicas
# ===========================================================================

def test_count_replicas_all_running() -> None:
    """count_replicas should count every pod that's Running."""
    pods: list[dict[str, Any]] = [
        _make_pod("brig-a", phase="Running"),
        _make_pod("brig-b", phase="Running"),
        _make_pod("brig-c", phase="Running"),
    ]
    assert count_replicas(pods) == 3


def test_count_replicas_some_not_running() -> None:
    """Only count the Running pods; skip Pending, Failed, etc."""
    pods: list[dict[str, Any]] = [
        _make_pod("brig-a", phase="Running"),
        _make_pod("brig-b", phase="Pending"),
        _make_pod("brig-c", phase="Running"),
    ]
    assert count_replicas(pods) == 2


def test_count_replicas_none_running() -> None:
    """No Running pods? Return 0."""
    pods: list[dict[str, Any]] = [
        _make_pod("brig-a", phase="Pending"),
        _make_pod("brig-b", phase="Failed"),
    ]
    assert count_replicas(pods) == 0


def test_count_replicas_empty_list() -> None:
    """Empty list of pods means 0 replicas."""
    assert count_replicas([]) == 0


# ===========================================================================
# PodCache class
# ===========================================================================

def test_pod_cache_returns_fetched_data() -> None:
    """PodCache.get_or_fetch returns the data from kubectl_fn."""
    cache: PodCache = PodCache()

    pod: dict[str, Any] = _make_pod("brig-abc-def")
    fetch_result: CommandResult = _cmd_result("pod json")

    def kubectl_fn(resource: str, **kwargs: Any) -> tuple[CommandResult, dict[str, Any]]:
        return (fetch_result, {"items": [pod]})

    cmd, pods = cache.get_or_fetch(kubectl_fn)
    assert cmd is fetch_result
    assert len(pods) == 1
    assert pods[0]["metadata"]["name"] == "brig-abc-def"


def test_pod_cache_caches_result() -> None:
    """Second call to get_or_fetch returns cached data without re-fetching."""
    cache: PodCache = PodCache()
    call_count: int = 0

    def kubectl_fn(resource: str, **kwargs: Any) -> tuple[CommandResult, dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        return (_cmd_result(), {"items": [_make_pod("brig-abc-def")]})

    # First call fetches
    cache.get_or_fetch(kubectl_fn)
    assert call_count == 1

    # Second call uses cache
    cache.get_or_fetch(kubectl_fn)
    assert call_count == 1


def test_pod_cache_clear_forces_refetch() -> None:
    """Clearing the cache makes the next get_or_fetch call kubectl again."""
    cache: PodCache = PodCache()
    call_count: int = 0

    def kubectl_fn(resource: str, **kwargs: Any) -> tuple[CommandResult, dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        return (_cmd_result(), {"items": []})

    cache.get_or_fetch(kubectl_fn)
    assert call_count == 1

    cache.clear()

    cache.get_or_fetch(kubectl_fn)
    assert call_count == 2


def test_pod_cache_empty_result_expires_fast() -> None:
    """Empty results expire after the short TTL."""
    import time

    # Use very short TTLs for testing
    cache: PodCache = PodCache(empty_ttl=0.05, nonempty_ttl=10.0)
    call_count: int = 0

    def kubectl_fn(resource: str, **kwargs: Any) -> tuple[CommandResult, dict[str, Any]]:
        nonlocal call_count
        call_count += 1
        return (_cmd_result(), {"items": []})

    cache.get_or_fetch(kubectl_fn)
    assert call_count == 1

    # Wait for empty TTL to expire
    time.sleep(0.06)

    cache.get_or_fetch(kubectl_fn)
    assert call_count == 2
