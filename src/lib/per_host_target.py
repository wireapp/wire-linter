"""Base class for targets that run the same check across multiple hosts.

One data point per host. You define which hosts to check via get_hosts()
and what to collect per host via collect_for_host(). The iteration lifecycle
is handled by IterableTarget.execute_all().

Related modules:
    iterable_target.py: Generic iteration template this class builds on.
    per_service_target.py: Same pattern for Wire service iteration.
    per_configmap_target.py: Same pattern for ConfigMap extraction.
"""

from __future__ import annotations

from typing import Any

from src.lib.iterable_target import IterableTarget, build_path_insert


class PerHostTarget(IterableTarget):
    """Base class for targets that iterate over multiple hosts.

    Subclasses implement get_hosts() and collect_for_host(). The runner
    calls execute_all() which produces one TargetResult per host with
    paths like '{prefix}/{host_name}/{filename}'.

    Example: vm/disk_usage.py checks disk on every VM and produces paths like
    vm/kubenode-192.168.122.235/disk_usage, vm/datanode-192.168.122.220/disk_usage.
    """

    # All per-host targets need SSH to reach the individual VMs
    requires_ssh: bool = True

    def get_hosts(self) -> list[dict[str, str]]:
        """Return the list of hosts to iterate over.

        Each host is a dict with at least 'name' (used in the path) and 'ip' (for SSH).

        Returns:
            List of host dicts, e.g.:
            [
                {"name": "kubenode-192.168.122.235", "ip": "192.168.122.235"},
                {"name": "datanode-192.168.122.220", "ip": "192.168.122.220"},
            ]
        """
        raise NotImplementedError("Subclasses must implement get_hosts()")

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Collect the data point value for a single host.

        Args:
            host: The host dict from get_hosts().

        Returns:
            The collected value for this host.
        """
        raise NotImplementedError("Subclasses must implement collect_for_host()")

    def description_for_host(self, host: dict[str, str]) -> str:
        """Generate description for a specific host.

        Override to customize. Default appends the host name to the base description.

        Args:
            host: The host dict from get_hosts().

        Returns:
            Host-specific description string.
        """
        return f"{self.description} on {host['name']} ({host['ip']})"

    # ── IterableTarget hooks ────────────────────────────────────

    def get_items(self) -> list[dict[str, str]]:
        """Delegate to get_hosts()."""
        return self.get_hosts()

    def collect_for_item(self, item: dict[str, str]) -> str | int | float | bool | None:
        """Delegate to collect_for_host()."""
        return self.collect_for_host(item)

    def path_for_item(self, item: dict[str, str]) -> str:
        """Insert host name between the path prefix and filename.

        For 'vm/disk_usage' with host 'kubenode1', produces 'vm/kubenode1/disk_usage'.
        For a single-segment path like 'status', produces 'kubenode1/status'.
        """
        return build_path_insert(self._path, item["name"])

    def description_for_item(self, item: dict[str, str]) -> str:
        """Delegate to description_for_host()."""
        return self.description_for_host(item)

    def extra_metadata_for_item(self, item: dict[str, str]) -> dict[str, Any]:
        """Include host_name and host_ip in each DataPoint's metadata."""
        return {"host_name": item["name"], "host_ip": item["ip"]}
