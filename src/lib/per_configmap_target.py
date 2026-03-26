"""Base class for targets that fetch the same type of data from multiple
Kubernetes ConfigMaps, emitting one data point per ConfigMap.

For each spec, one data point gets constructed with the path
<base_path>/<service_name>. The iteration lifecycle is handled by
IterableTarget.execute_all().

Related modules:
    iterable_target.py: Generic iteration template this class builds on.
    per_host_target.py: Same pattern for SSH host checks.
    per_service_target.py: Same pattern for Wire service iteration.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.lib.base_target import TargetResult
from src.lib.iterable_target import IterableTarget, build_path_append
from src.lib.output import DataPoint


class ConfigmapSpec(TypedDict):
    """Specification for a single ConfigMap to collect.

    Attributes:
        name:           Short slug used in the output path (e.g. 'brig').
                        Must be unique within a single target's list.
        configmap_name: The actual Kubernetes ConfigMap name (e.g. 'brig',
                        'sftd-join-call'). Can differ from `name`.
        namespace:      Kubernetes namespace to use. If None, uses the
                        namespace from the runner config.
        data_key:       Which key to extract from the ConfigMap .data.
                        If None, takes the first (and only) key.
        description:    Human-readable label for the data point.
    """

    name:           str
    configmap_name: str
    namespace:      str | None
    data_key:       str | None
    description:    str


class PerConfigmapTarget(IterableTarget):
    """Base class for targets that iterate over multiple Kubernetes ConfigMaps.

    Subclasses implement get_configmaps() to return which ConfigMaps to
    collect, and collect_for_configmap() to fetch the content of each.

    Path construction appends the name to the base path:
        'kubernetes/configmaps' + '/' + 'brig'
        => 'kubernetes/configmaps/brig'
    """

    # These targets use kubectl, not SSH
    requires_ssh: bool = False

    def get_configmaps(self) -> list[ConfigmapSpec]:
        """Return the list of ConfigMap specs to collect.

        Subclasses must override this. Each spec describes one ConfigMap
        and which data key to extract from it.

        Returns:
            Ordered list of ConfigmapSpec dicts.
        """
        raise NotImplementedError("Subclasses must implement get_configmaps()")

    def collect_for_configmap(self, spec: ConfigmapSpec) -> str | None:
        """Collect the content for a single ConfigMap.

        Args:
            spec: The ConfigmapSpec describing which ConfigMap to fetch.

        Returns:
            The extracted content string, or None if unavailable.
        """
        raise NotImplementedError("Subclasses must implement collect_for_configmap()")

    # ── IterableTarget hooks ────────────────────────────────────

    def get_items(self) -> list[ConfigmapSpec]:
        """Delegate to get_configmaps()."""
        return self.get_configmaps()

    def collect_for_item(self, item: ConfigmapSpec) -> str | None:
        """Delegate to collect_for_configmap()."""
        return self.collect_for_configmap(item)

    def path_for_item(self, item: ConfigmapSpec) -> str:
        """Append configmap name slug to the base path."""
        return build_path_append(self._path, item["name"])

    def description_for_item(self, item: ConfigmapSpec) -> str:
        """Use the description from the ConfigmapSpec."""
        return item["description"]

    def extra_metadata_for_item(self, item: ConfigmapSpec) -> dict[str, Any]:
        """Include configmap_name, namespace, and data_key in metadata."""
        return {
            "configmap_name": item["configmap_name"],
            "namespace": item.get("namespace") or self.config.cluster.kubernetes_namespace,
            "data_key": item.get("data_key") or "",
        }

    def on_none_value(
        self,
        item: ConfigmapSpec,
        path: str,
        description: str,
        metadata: dict[str, Any],
        duration_seconds: float,
    ) -> TargetResult | None:
        """Treat None as not_applicable — ConfigMap was absent or empty."""
        metadata["not_applicable"] = True
        configmap_name: str = item.get("configmap_name", item.get("name", "?"))
        self.terminal.target_not_applicable(
            path,
            f"ConfigMap '{configmap_name}' not found or could not be parsed",
        )

        na_dp: DataPoint = DataPoint(
            path=path,
            value=None,
            unit="",
            description=description,
            raw_output="\n".join(self._raw_outputs),
            metadata=metadata,
        )

        return TargetResult(
            data_point=na_dp,
            success=True,
            error=None,
            duration_seconds=round(duration_seconds, 3),
        )

    def on_item_success(self, item: ConfigmapSpec, value: Any) -> str:
        """Show content preview then return char count summary."""
        self.terminal.command_result(value)
        return f"{len(value)} chars"
