"""Lists all Wire services deployed in the Kubernetes cluster.

Queries deployments, statefulsets, and daemonsets across all namespaces
and filters to known Wire-related workload names.  This covers
multi-namespace deployments where RabbitMQ, cert-manager, ingress-nginx,
etc. live outside the main Wire namespace.

The value is a comma-separated list of service names; full details
(name, namespace, type, desired/ready replicas) are in raw_output and
metadata.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.kubectl import int_or_zero


# Workload resource types we need to query, paired with their canonical
# Kubernetes kind labels. Stored as tuples because capitalize() mangles
# multi-word kinds like StatefulSet and DaemonSet.
_WORKLOAD_TYPES: list[tuple[str, str]] = [
    ("deployments",  "Deployment"),
    ("statefulsets", "StatefulSet"),
    ("daemonsets",   "DaemonSet"),
]

# Known Wire-related workload name prefixes. Workloads whose name starts
# with any of these are considered part of a Wire installation. This lets
# us query all namespaces and still filter out unrelated cluster workloads
# (system controllers, monitoring agents, etc.).
_WIRE_NAME_PREFIXES: tuple[str, ...] = (
    # Core Wire services
    "brig",
    "galley",
    "gundeck",
    "cannon",
    "cargohold",
    "spar",
    "nginz",
    "webapp",
    "team-settings",
    "account-pages",
    "background-worker",
    "sftd",
    "coturn",
    "wire-server",
    "federator",
    # Supporting infrastructure commonly deployed alongside Wire
    "cassandra",
    "elasticsearch",
    "minio",
    "rabbitmq",
    "redis",
    "cert-manager",
    "ingress-nginx",
    "fake-aws",
    "demo-smtp",
    "reaper",
    "restund",
)


def _is_wire_workload(name: str) -> bool:
    """Return True if the workload name matches a known Wire-related prefix.

    Uses startswith matching so that names like 'brig-7f6b9d4c5-xz9qp' or
    'rabbitmq-server' are correctly identified.
    """
    return name.startswith(_WIRE_NAME_PREFIXES)


def _get_replica_counts(item: dict[str, Any], resource_type: str) -> tuple[int, int]:
    """Extract desired and ready replica counts from a workload resource.

    DaemonSets are different from Deployments/StatefulSets they use different
    status fields. DaemonSets don't have spec.replicas because they schedule
    one pod per node.
    """
    status: dict[str, Any] = item.get("status", {})

    if resource_type == "daemonsets":
        # DaemonSets use desiredNumberScheduled/numberReady
        desired: int = int_or_zero(status, "desiredNumberScheduled")
        ready: int   = int_or_zero(status, "numberReady")
    else:
        # Deployments and StatefulSets use spec.replicas and readyReplicas
        desired = int_or_zero(item.get("spec", {}), "replicas")
        ready   = int_or_zero(status, "readyReplicas")

    return desired, ready


class ServiceList(BaseTarget):
    """Lists all Wire services deployed in the cluster.

    Queries deployments, statefulsets, and daemonsets across all namespaces
    and filters to known Wire-related names.  Returns the service names as
    a comma-separated string so the value remains a JSON primitive.
    """

    @property
    def description(self) -> str:
        """What we collect."""
        return "List of deployed Wire services"

    @property
    def explanation(self) -> str:
        """We need a full inventory of what's running. Missing services mean failed deployments or accidental deletes. Under-replicated services point to capacity problems."""
        return (
            "A complete inventory of deployed services. Missing services indicate "
            "failed deployments or accidental deletions. Under-replicated services "
            "signal capacity issues."
        )

    def collect(self) -> str:
        """Query all workload types across all namespaces and return a combined service list."""
        services: list[tuple[str, str, str, int, int]] = []

        for resource_type, kind in _WORKLOAD_TYPES:
            # Query across all namespaces so we catch Wire components
            # deployed outside the main Wire namespace (rabbitmq,
            # cert-manager, ingress-nginx, etc.)
            cmd_result, data = self.run_kubectl(resource_type, all_namespaces=True)

            if data is None:
                raise RuntimeError(f"Failed to query {resource_type} from kubectl")

            items: list[dict[str, Any]] = data.get("items", [])

            for item in items:
                metadata: dict[str, Any] = item.get("metadata", {})
                name: str = metadata.get("name", "unknown")

                # Skip workloads that aren't part of a Wire installation
                if not _is_wire_workload(name):
                    continue

                namespace: str = metadata.get("namespace", "unknown")
                desired, ready = _get_replica_counts(item, resource_type)
                services.append((name, namespace, kind, desired, ready))

        # Sort alphabetically for consistent output
        services.sort(key=lambda s: s[0])

        # Build detail lines for display, including namespace for clarity
        detail_lines: list[str] = [
            f"{name} ({namespace}/{kind}, {ready}/{desired} ready)"
            for name, namespace, kind, desired, ready in services
        ]

        # Preserve rich detail in raw_output so the UI details panel can show
        # namespace, kind, and replica counts rather than just service names
        self._track_output("service inventory", "\n".join(detail_lines))

        # Track under-replicated services for health info
        under_replicated: list[str] = [
            name for name, namespace, kind, desired, ready in services
            if ready < desired
        ]

        if under_replicated:
            self._health_info = (
                f"{len(services)} services, "
                f"{len(under_replicated)} under-replicated: {', '.join(under_replicated)}"
            )
        else:
            self._health_info = f"{len(services)} services, all fully replicated"

        service_names: list[str] = [name for name, namespace, kind, desired, ready in services]
        return ", ".join(service_names)
