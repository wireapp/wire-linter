"""Base class for targets that iterate over Wire service names,
emitting one data point per service.

For each service, one data point gets constructed with the path
<base_path>/<service_name>. The iteration lifecycle is handled by
IterableTarget.execute_all().

Related modules:
    iterable_target.py: Generic iteration template this class builds on.
    per_host_target.py: Same pattern for SSH host checks.
    per_configmap_target.py: Same pattern for ConfigMap extraction.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.lib.iterable_target import IterableTarget, build_path_append


class ServiceSpec(TypedDict):
    """Specification for a single Wire service to iterate over.

    Attributes:
        name:        Short slug used in the output path (e.g. 'brig').
                     Must be unique within a single target's list.
        description: Human-readable label for the data point.
    """

    name:        str
    description: str


# The 8 core Wire services deployed as Deployments in Kubernetes.
# Shared across all PerServiceTarget subclasses so the same list
# gets iterated consistently.
WIRE_CORE_SERVICES: list[ServiceSpec] = [
    {"name": "brig",              "description": "Brig (user accounts)"},
    {"name": "galley",            "description": "Galley (conversations)"},
    {"name": "gundeck",           "description": "Gundeck (push notifications)"},
    {"name": "cannon",            "description": "Cannon (WebSocket push)"},
    {"name": "cargohold",         "description": "Cargohold (asset storage)"},
    {"name": "spar",              "description": "Spar (SSO / SAML / SCIM)"},
    {"name": "nginz",             "description": "Nginz (API gateway)"},
    {"name": "background-worker", "description": "Background Worker"},
]


class PerServiceTarget(IterableTarget):
    """Base class for targets that iterate over Wire services.

    Subclasses implement get_services() to return which services to
    check, and collect_for_service() to gather data for each one.

    Path construction appends the service name to the base path:
        'kubernetes/deployments/template_annotations' + '/' + 'brig'
        => 'kubernetes/deployments/template_annotations/brig'
    """

    # These targets use kubectl, not SSH
    requires_ssh: bool = False

    def get_services(self) -> list[ServiceSpec]:
        """Return the list of service specs to iterate over.

        Subclasses must override this. Each spec describes one service
        and becomes one data point in the output.

        Returns:
            Ordered list of ServiceSpec dicts.
        """
        raise NotImplementedError("Subclasses must implement get_services()")

    def collect_for_service(self, spec: ServiceSpec) -> str | int | float | bool | None:
        """Collect data for a single service.

        Args:
            spec: The ServiceSpec describing which service to check.

        Returns:
            The collected value (None is a valid value).

        Raises:
            NotApplicableError: When the service doesn't exist.
            Any exception -- execute_all() catches it and records an error.
        """
        raise NotImplementedError("Subclasses must implement collect_for_service()")

    # ── IterableTarget hooks ────────────────────────────────────

    def get_items(self) -> list[ServiceSpec]:
        """Delegate to get_services()."""
        return self.get_services()

    def collect_for_item(self, item: ServiceSpec) -> str | int | float | bool | None:
        """Delegate to collect_for_service()."""
        return self.collect_for_service(item)

    def path_for_item(self, item: ServiceSpec) -> str:
        """Append service name to the base path."""
        return build_path_append(self._path, item["name"])

    def description_for_item(self, item: ServiceSpec) -> str:
        """Use the description from the ServiceSpec."""
        return item["description"]

    def extra_metadata_for_item(self, item: ServiceSpec) -> dict[str, Any]:
        """Include service_name in each DataPoint's metadata."""
        return {"service_name": item["name"]}

    def on_item_success(self, item: ServiceSpec, value: Any) -> str:
        """Truncate display value to 80 chars for readability."""
        return str(value)[:80]
