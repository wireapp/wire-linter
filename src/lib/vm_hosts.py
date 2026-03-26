"""Discovers all VM hosts (kubenodes and datanodes) that need checking.

Gets hosts from two places: Kubernetes nodes (via kubectl or explicit config.nodes.kube_nodes)
and data nodes (from config.nodes.data_nodes or the cassandra/elasticsearch/minio/postgresql
IPs). Names everything by IP for consistency kubenode-{ip} and datanode-{ip}.

If a machine shows up in both lists, kubenode wins and it's only added once.

Also exports discover_kube_node_ips() for shared kubectl-based node discovery,
used by both discover_vm_hosts() and BaseTarget.get_first_kube_node_ip().
"""

from __future__ import annotations

from typing import Any, Callable

from src.lib.config import Config


def discover_kube_node_ips(
    kubectl_fn: Callable[..., tuple[Any, Any]],
) -> list[str]:
    """Discover kube node InternalIPs via kubectl get nodes.

    Calls kubectl to list nodes and extracts InternalIP addresses from each.
    Shared by discover_vm_hosts() and BaseTarget.get_first_kube_node_ip()
    so the kubectl+address-parsing logic lives in one place.

    Args:
        kubectl_fn: Callable that runs kubectl and returns (CommandResult, parsed_json).

    Returns:
        List of InternalIP address strings (may be empty if kubectl fails
        or no nodes have an InternalIP).
    """
    _cmd_result, data = kubectl_fn("nodes")

    if data is None:
        return []

    ips: list[str] = []
    items: list[dict[str, Any]] = data.get("items", [])
    for item in items:
        # Pull out the InternalIP from the addresses list
        addresses: list[dict[str, str]] = item.get("status", {}).get("addresses", [])
        for addr in addresses:
            if addr.get("type") == "InternalIP":
                ip: str | None = addr.get("address")
                if ip:
                    ips.append(ip)
                break

    return ips


def discover_vm_hosts(
    config: Config,
    kubectl_fn: Callable[..., tuple[Any, Any]],
) -> list[dict[str, str]]:
    """Discover all VM hosts that should be checked.

    Prefers explicit config.nodes lists, falls back to kubectl for kubenodes and
    config.databases IPs for datanodes. Everything gets named by IP address so paths
    stay consistent regardless of cluster-specific node names.

    Args:
        config: The runner configuration.
        kubectl_fn: Callable that runs kubectl and returns (CommandResult, parsed_json).

    Returns:
        List of dicts with 'name' and 'ip' keys.
    """
    # Track IPs we've already seen so we don't add duplicates
    seen_ips: set[str] = set()
    # Build up the list of hosts
    hosts: list[dict[str, str]] = []

    # Get kubenodes from explicit config or kubectl
    if config.nodes.kube_nodes:
        # Use the explicit list if provided
        for ip in config.nodes.kube_nodes:
            if ip not in seen_ips:
                hosts.append({"name": f"kubenode-{ip}", "ip": ip})
                seen_ips.add(ip)
    else:
        # Fall back to kubectl get nodes via the shared helper
        for ip in discover_kube_node_ips(kubectl_fn):
            # Guard against duplicate IPs (e.g. cluster misconfiguration)
            if ip not in seen_ips:
                hosts.append({"name": f"kubenode-{ip}", "ip": ip})
                seen_ips.add(ip)

    # Get datanodes from explicit config or database IPs
    if config.nodes.data_nodes:
        # Use the explicit list if provided
        for ip in config.nodes.data_nodes:
            if ip not in seen_ips:
                hosts.append({"name": f"datanode-{ip}", "ip": ip})
                seen_ips.add(ip)
    else:
        # Pull database IPs from config skip any that already showed up as kubenodes.
        # rabbitmq is included because it may run on dedicated broker VMs with a distinct IP.
        db_ips: list[str] = [
            config.databases.cassandra,
            config.databases.elasticsearch,
            config.databases.minio,
            config.databases.postgresql,
            config.databases.rabbitmq,
        ]

        for ip in db_ips:
            if ip and ip not in seen_ips:
                hosts.append({"name": f"datanode-{ip}", "ip": ip})
                seen_ips.add(ip)

    return hosts
