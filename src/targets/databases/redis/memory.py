"""Checks Redis memory usage and eviction status.

When Redis starts evicting keys, sessions and caches just vanish, and
users get randomly kicked out. We use kubectl exec to hit redis-cli.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


def _has_redis_container(pod: dict[str, Any]) -> bool:
    """Check whether a pod spec includes a container named 'redis'.

    The actual Redis server pod always has a container called 'redis',
    while sidecars (redis-exporter, sentinel) and unrelated pods
    (redis-commander) use different container names. This lets the
    name-based search reject non-server pods.
    """
    containers: list[dict[str, Any]] = (
        pod.get("spec", {}).get("containers", [])
    )
    return any(c.get("name") == "redis" for c in containers)


def _is_running(pod: dict[str, Any]) -> bool:
    """Check whether a pod is in the Running phase."""
    return pod.get("status", {}).get("phase") == "Running"


class RedisMemory(BaseTarget):
    """Checks Redis memory usage and eviction status.

    Runs redis-cli info all inside the Redis pod via kubectl exec
    and reports used memory and evicted key count.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Redis memory usage and eviction status"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Eviction = sessions and caches gone = users drop out randomly. "
            "We're good when evicted_keys is zero."
        )

    def collect(self) -> str:
        """Check Redis memory usage via kubectl exec.

        Returns:
            Memory usage summary string.

        Raises:
            RuntimeError: If Redis pod cannot be found or queried.
        """
        self.terminal.step("Checking Redis memory usage...")

        # Find which Redis pod we're talking to
        cmd_result, data = self.run_kubectl(
            "pods",
            selector="app=redis",
            all_namespaces=True,
        )

        # Try a broader selector if the first one doesn't match
        if data is None or not data.get("items"):
            cmd_result, data = self.run_kubectl(
                "pods",
                selector="app.kubernetes.io/name=redis",
                all_namespaces=True,
            )

        if data is None or not data.get("items"):
            # Last try: search all pods for "redis" in the name, but only
            # accept pods that have a container named "redis" to avoid matching
            # Redis Sentinel, redis-exporter sidecars, or redis-commander
            cmd_result_all, data_all = self.run_kubectl("pods", all_namespaces=True)
            if data_all:
                redis_pods: list[dict[str, Any]] = [
                    p for p in data_all.get("items", [])
                    if "redis" in p.get("metadata", {}).get("name", "").lower()
                    and _has_redis_container(p)
                ]
                if redis_pods:
                    data = {"items": redis_pods}

        if data is None or not data.get("items"):
            raise RuntimeError("No Redis pods found")

        # Filter to Running pods only — a pod in CrashLoopBackOff, Pending,
        # or Terminating would cause kubectl exec to fail with an unhelpful error
        running_pods: list[dict[str, Any]] = [
            p for p in data["items"] if _is_running(p)
        ]
        if not running_pods:
            raise RuntimeError(
                f"No running Redis pod found ({len(data['items'])} pod(s) exist "
                "but none are in Running phase)"
            )

        pod_name: str = running_pods[0]["metadata"]["name"]
        namespace: str = running_pods[0]["metadata"].get("namespace") or self.config.cluster.kubernetes_namespace

        # Get all stats from redis-cli in one call, targeting the 'redis' container
        # explicitly in case the pod has sidecars (exporter, sentinel).
        # We need "info all" rather than "info memory" because evicted_keys lives
        # in the stats section, not the memory section.
        result = self.run_kubectl_raw([
            "exec", pod_name, "-c", "redis", "-n", namespace, "--",
            "redis-cli", "info", "all",
        ])

        output: str = result.stdout.strip()

        # Pull out the important memory numbers
        used_memory_human: str = ""
        maxmemory_human: str = ""
        evicted_keys: int = 0

        for line in output.split("\n"):
            if line.startswith("used_memory_human:"):
                used_memory_human = line.split(":", 1)[1].strip()
            elif line.startswith("maxmemory_human:"):
                maxmemory_human = line.split(":", 1)[1].strip()
            elif line.startswith("evicted_keys:"):
                try:
                    evicted_keys = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

        # Valid redis-cli info all output always contains used_memory_human.
        # If it's missing, redis-cli likely failed (auth error, connection refused, etc.)
        if not used_memory_human:
            raise RuntimeError(
                f"redis-cli info all returned unexpected output: {output[:200]}"
            )

        # Assemble the summary string
        summary_parts: list[str] = []
        summary_parts.append(f"used={used_memory_human}")
        if maxmemory_human:
            summary_parts.append(f"max={maxmemory_human}")
        summary_parts.append(f"evicted={evicted_keys}")

        summary: str = ", ".join(summary_parts)

        if evicted_keys > 0:
            self._health_info = f"WARNING: {evicted_keys} keys evicted - {summary}"
        else:
            self._health_info = summary

        return summary
