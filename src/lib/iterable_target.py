"""Base class for targets that produce one data point per item in a list.

Unifies the execute_all() lifecycle that was previously duplicated across
PerHostTarget, PerServiceTarget, and PerConfigmapTarget. Subclasses define
what the items are (hosts, services, configmaps) and how to collect data
for each one. The execute_all() template method handles the common lifecycle:
discovery, iteration, error handling, terminal output, and result building.

Related modules:
    per_host_target.py:      IterableTarget for SSH host checks.
    per_service_target.py:   IterableTarget for Wire service iteration.
    per_configmap_target.py: IterableTarget for ConfigMap extraction.
    target_discovery.py:     Checks isinstance(target, IterableTarget)
      to decide between execute() and execute_all().
    base_target.py:          Parent class with command helpers and lifecycle.
"""

from __future__ import annotations

import time
from typing import Any

from src.lib.base_target import BaseTarget, NotApplicableError, TargetResult, now_utc_str
from src.lib.output import DataPoint


def build_path_insert(base_path: str, item_name: str) -> str:
    """Build a per-item path by inserting the item name between prefix and filename.

    PerHostTarget uses this to produce paths like 'vm/kubenode1/disk_usage'
    from base path 'vm/disk_usage' and item name 'kubenode1'.

    For multi-segment paths: splits on the last '/', inserts the item name
    between the prefix and filename.

    For single-segment paths: prepends the item name.

    Args:
        base_path: The target's base path (e.g. 'vm/disk_usage' or 'status').
        item_name: The name to insert (e.g. 'kubenode1').

    Returns:
        The constructed path string.

    Examples:
        >>> build_path_insert('vm/disk_usage', 'kubenode1')
        'vm/kubenode1/disk_usage'
        >>> build_path_insert('check/deep/nested', 'host1')
        'check/deep/host1/nested'
        >>> build_path_insert('status', 'node1')
        'node1/status'
    """
    if "/" in base_path:
        prefix, filename = base_path.rsplit("/", 1)
        return f"{prefix}/{item_name}/{filename}"
    return f"{item_name}/{base_path}"


def build_path_append(base_path: str, item_name: str) -> str:
    """Build a per-item path by appending the item name to the base path.

    PerServiceTarget and PerConfigmapTarget use this to produce paths like
    'wire_services/healthy/brig' from base path 'wire_services/healthy' and
    item name 'brig'.

    Args:
        base_path: The target's base path (e.g. 'wire_services/healthy').
        item_name: The name to append (e.g. 'brig').

    Returns:
        The constructed path string.

    Examples:
        >>> build_path_append('wire_services/healthy', 'brig')
        'wire_services/healthy/brig'
        >>> build_path_append('config', 'brig')
        'config/brig'
    """
    return f"{base_path}/{item_name}"


class IterableTarget(BaseTarget):
    """Base class for targets that iterate over a list of items.

    Each item produces one DataPoint. Subclasses implement five hooks:

        get_items()              -> list of items to iterate over
        collect_for_item(item)   -> collected value for one item
        path_for_item(item)      -> data point path for one item
        description_for_item(item) -> human-readable description
        extra_metadata_for_item(item) -> additional metadata keys

    Optionally override:
        on_item_success(item, value) -> display string for terminal
        on_none_value(item, path, description, metadata, duration)
            -> TargetResult if None needs special handling, else None
    """

    @property
    def is_iterable(self) -> bool:
        """Marker for the discovery system to identify iterable targets."""
        return True

    # Kept for backward compatibility with target_discovery.py which
    # checks is_per_host on instantiated targets
    @property
    def is_per_host(self) -> bool:
        """Backward-compatible alias for is_iterable."""
        return True

    # ── Hooks for subclasses ────────────────────────────────────

    def get_items(self) -> list[Any]:
        """Return the list of items to iterate over.

        Each item becomes one DataPoint in the output. Override in subclass.

        Returns:
            List of items (hosts, service specs, configmap specs, etc.).
        """
        raise NotImplementedError("Subclasses must implement get_items()")

    def collect_for_item(self, item: Any) -> str | int | float | bool | None:
        """Collect data for a single item.

        Args:
            item: One element from get_items().

        Returns:
            The collected value for this item.
        """
        raise NotImplementedError("Subclasses must implement collect_for_item()")

    def path_for_item(self, item: Any) -> str:
        """Build the data point path for an item.

        Args:
            item: One element from get_items().

        Returns:
            Hierarchical path string (e.g. 'vm/kubenode1/disk_usage').
        """
        raise NotImplementedError("Subclasses must implement path_for_item()")

    def description_for_item(self, item: Any) -> str:
        """Build the human-readable description for an item's DataPoint.

        Args:
            item: One element from get_items().

        Returns:
            Description string.
        """
        raise NotImplementedError("Subclasses must implement description_for_item()")

    def extra_metadata_for_item(self, item: Any) -> dict[str, Any]:
        """Return additional metadata keys specific to this item type.

        Override in subclasses to add keys like host_name, service_name, etc.
        The default returns an empty dict.

        Args:
            item: One element from get_items().

        Returns:
            Dict of extra metadata keys to merge into the DataPoint metadata.
        """
        return {}

    def on_item_success(self, item: Any, value: Any) -> str:
        """Format the display value shown in the terminal after success.

        Override to customize how the collected value is summarized.
        The default converts to string.

        Args:
            item: One element from get_items().
            value: The value returned by collect_for_item().

        Returns:
            Display string for terminal output.
        """
        return str(value)

    def on_none_value(
        self,
        item: Any,
        path: str,
        description: str,
        metadata: dict[str, Any],
        duration_seconds: float,
    ) -> TargetResult | None:
        """Handle a None return value from collect_for_item().

        Override in subclasses that treat None specially (e.g. PerConfigmapTarget
        treats None as not_applicable). Return a TargetResult to short-circuit
        the normal success path, or None to continue with the default behavior.

        Args:
            item: The item that produced the None value.
            path: The data point path for this item.
            description: The resolved description string.
            metadata: The base metadata dict (already built).
            duration_seconds: Elapsed time for this item's collection.

        Returns:
            A TargetResult to use instead of the default, or None.
        """
        return None

    # ── Template method ─────────────────────────────────────────

    def execute_all(self) -> list[TargetResult]:
        """Execute this target for every item from get_items().

        Template method that handles the full lifecycle: reset accumulators,
        check skip guards, discover items, iterate with error handling,
        build DataPoints and TargetResults. Subclasses customize behavior
        through the hooks above.

        Returns:
            List of TargetResults, one per item.
        """
        # Reset accumulators before skip guards so stale state from a prior
        # run doesn't leak into skip-result metadata
        self._reset_accumulators()

        # When running in k8s-only mode or from admin host, some targets
        # should be skipped entirely
        skip_result: list[TargetResult] | None = self._check_execute_all_skip()
        if skip_result is not None:
            return skip_result

        # Discover the items to iterate over. Wrap in try/except so
        # discovery failures (kubectl unreachable, network errors) produce
        # a TargetResult instead of crashing the runner.
        overall_start: float = time.monotonic()
        try:
            items: list[Any] = self.get_items()
        except Exception as discovery_error:
            return [self._build_discovery_error_result(overall_start, discovery_error)]

        results: list[TargetResult] = []

        # Print the explanation once, after the first target_start header
        explanation_printed: bool = False

        for item in items:
            item_path: str = self.path_for_item(item)
            item_start: float = time.monotonic()

            # Print the target header for this item
            self.terminal.target_start(item_path)

            # Show the explanation once on the first iteration
            if not explanation_printed:
                explanation_printed = True
                if self.explanation is not None:
                    self.terminal.target_explanation(self.explanation)

            # Reset accumulators per item — each gets independent output
            self._reset_accumulators()

            try:
                value: str | int | float | bool | None = self.collect_for_item(item)

                # Resolve description — dynamic override takes precedence
                item_description: str = (
                    self._dynamic_description
                    if self._dynamic_description is not None
                    else self.description_for_item(item)
                )

                # Build metadata with shared helper + item-specific extras
                metadata: dict[str, Any] = self._build_base_metadata(item_start)
                metadata.update(self.extra_metadata_for_item(item))

                # Let subclass handle None values specially (e.g. not_applicable)
                if value is None:
                    override: TargetResult | None = self.on_none_value(
                        item, item_path, item_description, metadata,
                        metadata["duration_seconds"],
                    )
                    if override is not None:
                        results.append(override)
                        continue

                # Display success in the terminal
                display_value: str = self.on_item_success(item, value)
                self.terminal.target_success(item_path, display_value, self.unit)

                # Print health assessment if the target provided one
                if self._health_info is not None:
                    self.terminal.health_info(self._health_info)

                # Build the DataPoint for this item
                dp: DataPoint = DataPoint(
                    path=item_path,
                    value=value,
                    unit=self.unit,
                    description=item_description,
                    raw_output="\n".join(self._raw_outputs),
                    metadata=metadata,
                )

                results.append(TargetResult(
                    data_point=dp,
                    success=True,
                    error=None,
                    duration_seconds=metadata["duration_seconds"],
                ))

            except NotApplicableError as na_error:
                # Emit a not_applicable sentinel so the UI greys it out.
                # target_start() already printed the header, so pass
                # emit=False to avoid a duplicate terminal line.
                self.terminal.target_not_applicable(item_path, na_error.reason)
                results.append(self._build_not_applicable_result(
                    path=item_path,
                    reason=na_error.reason,
                    start_time=item_start,
                    extra_metadata=self.extra_metadata_for_item(item),
                    emit_not_applicable_line=False,
                ))

            except Exception as error:
                self.terminal.target_failure(item_path, str(error))

                # Safe fallback for description
                try:
                    error_description: str = (
                        self._dynamic_description
                        if self._dynamic_description is not None
                        else self.description_for_item(item)
                    )
                except Exception:
                    error_description = ""

                # Build error metadata with shared helper + item extras
                error_metadata: dict[str, Any] = self._build_base_metadata(
                    item_start, error=str(error),
                )
                error_metadata.update(self.extra_metadata_for_item(item))

                error_dp: DataPoint = DataPoint(
                    path=item_path,
                    value=None,
                    unit=self.unit,
                    description=error_description,
                    raw_output="\n".join(self._raw_outputs),
                    metadata=error_metadata,
                )

                results.append(TargetResult(
                    data_point=error_dp,
                    success=False,
                    error=str(error),
                    duration_seconds=error_metadata["duration_seconds"],
                ))

        return results

    def _build_discovery_error_result(
        self,
        start_time: float,
        error: Exception,
    ) -> TargetResult:
        """Build a TargetResult when get_items() fails.

        Args:
            start_time: Monotonic timestamp from before the discovery attempt.
            error: The exception that get_items() raised.

        Returns:
            A failed TargetResult with the error details.
        """
        self.terminal.target_start(self._path)
        self.terminal.target_failure(self._path, str(error))

        error_metadata: dict[str, Any] = self._build_base_metadata(
            start_time, error=str(error),
        )

        error_dp: DataPoint = DataPoint(
            path=self._path,
            value=None,
            unit=self.unit,
            description="",
            raw_output="",
            metadata=error_metadata,
        )

        return TargetResult(
            data_point=error_dp,
            success=False,
            error=str(error),
            duration_seconds=error_metadata["duration_seconds"],
        )
