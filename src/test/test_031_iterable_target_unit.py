"""Unit tests for the iterable_target module.

Tests the IterableTarget template method (execute_all), including success paths,
error handling, discovery failures, NotApplicableError, the on_none_value hook,
and the helper methods now_utc_str, _reset_accumulators, and _build_base_metadata.
"""

from __future__ import annotations

from typing import Any

from src.lib.base_target import BaseTarget, NotApplicableError, TargetResult, now_utc_str
from src.lib.iterable_target import IterableTarget, build_path_insert, build_path_append
from src.lib.logger import Logger, LogLevel
from src.lib.output import DataPoint
from src.lib.per_configmap_target import ConfigmapSpec, PerConfigmapTarget
from src.lib.per_host_target import PerHostTarget
from src.lib.per_service_target import PerServiceTarget, ServiceSpec
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_make_config = make_minimal_config


def _make_terminal() -> Terminal:
    """Quiet terminal for test output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Silent logger for tests."""
    return Logger(level=LogLevel.ERROR)


# ---------------------------------------------------------------------------
# Concrete test subclasses
# ---------------------------------------------------------------------------

class _SimpleIterableTarget(IterableTarget):
    """Minimal iterable target for testing the template method."""

    @property
    def description(self) -> str:
        return "Simple iterable"

    @property
    def unit(self) -> str:
        return "items"

    def get_items(self) -> list[dict[str, str]]:
        return [
            {"id": "a", "label": "Item A"},
            {"id": "b", "label": "Item B"},
        ]

    def collect_for_item(self, item: dict[str, str]) -> str:
        return f"value-{item['id']}"

    def path_for_item(self, item: dict[str, str]) -> str:
        return f"{self._path}/{item['id']}"

    def description_for_item(self, item: dict[str, str]) -> str:
        return item["label"]

    def extra_metadata_for_item(self, item: dict[str, str]) -> dict[str, Any]:
        return {"item_id": item["id"]}


class _FailingItemTarget(IterableTarget):
    """Target where the second item fails."""

    @property
    def description(self) -> str:
        return "Failing item"

    def get_items(self) -> list[dict[str, str]]:
        return [{"id": "ok"}, {"id": "fail"}]

    def collect_for_item(self, item: dict[str, str]) -> str:
        if item["id"] == "fail":
            raise RuntimeError("item failed")
        return "good"

    def path_for_item(self, item: dict[str, str]) -> str:
        return f"{self._path}/{item['id']}"

    def description_for_item(self, item: dict[str, str]) -> str:
        return f"Check {item['id']}"


class _DiscoveryFailsTarget(IterableTarget):
    """Target where get_items() raises."""

    @property
    def description(self) -> str:
        return "Discovery fails"

    def get_items(self) -> list[Any]:
        raise RuntimeError("discovery broken")

    def collect_for_item(self, item: Any) -> str:
        return "never"

    def path_for_item(self, item: Any) -> str:
        return "never"

    def description_for_item(self, item: Any) -> str:
        return "never"


class _NotApplicableItemTarget(IterableTarget):
    """Target where one item raises NotApplicableError."""

    @property
    def description(self) -> str:
        return "NA item"

    def get_items(self) -> list[dict[str, str]]:
        return [{"id": "ok"}, {"id": "na"}]

    def collect_for_item(self, item: dict[str, str]) -> str:
        if item["id"] == "na":
            raise NotApplicableError("service not deployed")
        return "collected"

    def path_for_item(self, item: dict[str, str]) -> str:
        return f"{self._path}/{item['id']}"

    def description_for_item(self, item: dict[str, str]) -> str:
        return f"Check {item['id']}"


class _NoneValueTarget(IterableTarget):
    """Target that returns None and uses the on_none_value hook."""

    @property
    def description(self) -> str:
        return "None handler"

    def get_items(self) -> list[dict[str, str]]:
        return [{"id": "empty"}]

    def collect_for_item(self, item: dict[str, str]) -> str | None:
        return None

    def path_for_item(self, item: dict[str, str]) -> str:
        return f"{self._path}/{item['id']}"

    def description_for_item(self, item: dict[str, str]) -> str:
        return "Empty item"

    def on_none_value(
        self, item: Any, path: str, description: str,
        metadata: dict[str, Any], duration_seconds: float,
    ) -> TargetResult | None:
        """Override: treat None as not_applicable."""
        dp: DataPoint = DataPoint(
            path=path, value=None, unit="",
            description=description, raw_output="",
            metadata=metadata,
        )
        return TargetResult(
            data_point=dp, success=True, error=None,
            duration_seconds=duration_seconds,
        )


class _WithExplanationTarget(IterableTarget):
    """Target that provides an explanation."""

    @property
    def description(self) -> str:
        return "With explanation"

    @property
    def explanation(self) -> str:
        return "This checks something important"

    def get_items(self) -> list[dict[str, str]]:
        return [{"id": "x"}]

    def collect_for_item(self, item: dict[str, str]) -> str:
        return "data"

    def path_for_item(self, item: dict[str, str]) -> str:
        return f"{self._path}/{item['id']}"

    def description_for_item(self, item: dict[str, str]) -> str:
        return "Item X"


# ---------------------------------------------------------------------------
# now_utc_str tests
# ---------------------------------------------------------------------------

def test_now_utc_str_format() -> None:
    """now_utc_str returns a properly formatted UTC timestamp."""
    ts: str = now_utc_str()

    # Format is YYYY-MM-DDTHH:MM:SSZ
    assert ts.endswith("Z")
    assert "T" in ts
    assert len(ts) == 20


def test_now_utc_str_is_utc() -> None:
    """now_utc_str returns UTC time, not local time."""
    import datetime
    ts: str = now_utc_str()

    # Parse and verify it's close to now (within a second)
    parsed: datetime.datetime = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    now: datetime.datetime = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    diff: float = abs((now - parsed).total_seconds())
    assert diff < 2, f"Timestamp {ts} is {diff}s from now"


# ---------------------------------------------------------------------------
# _reset_accumulators tests
# ---------------------------------------------------------------------------

def test_reset_accumulators_clears_state() -> None:
    """_reset_accumulators clears all four accumulator fields."""
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )

    # Populate with junk
    target._raw_outputs = ["leftover"]
    target._commands_run = ["old cmd"]
    target._dynamic_description = "old desc"
    target._health_info = "old info"

    target._reset_accumulators()

    assert target._raw_outputs == []
    assert target._commands_run == []
    assert target._dynamic_description is None
    assert target._health_info is None


# ---------------------------------------------------------------------------
# _build_base_metadata tests
# ---------------------------------------------------------------------------

def test_build_base_metadata_standard_fields() -> None:
    """_build_base_metadata includes the standard metadata fields."""
    import time
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/meta"

    start: float = time.monotonic()
    meta: dict[str, Any] = target._build_base_metadata(start)

    assert "collected_at" in meta
    assert "commands" in meta
    assert "duration_seconds" in meta
    assert "gathered_from" in meta
    assert isinstance(meta["commands"], list)
    assert isinstance(meta["duration_seconds"], float)


def test_build_base_metadata_includes_explanation() -> None:
    """_build_base_metadata includes explanation when the target provides one."""
    import time
    target: _WithExplanationTarget = _WithExplanationTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/expl"

    meta: dict[str, Any] = target._build_base_metadata(time.monotonic())
    assert meta["explanation"] == "This checks something important"


def test_build_base_metadata_no_explanation_when_none() -> None:
    """_build_base_metadata omits explanation when the target returns None."""
    import time
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/noexpl"

    meta: dict[str, Any] = target._build_base_metadata(time.monotonic())
    assert "explanation" not in meta


def test_build_base_metadata_includes_health_info() -> None:
    """_build_base_metadata includes health_info when set."""
    import time
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._health_info = "All replicas running"

    meta: dict[str, Any] = target._build_base_metadata(time.monotonic())
    assert meta["health_info"] == "All replicas running"


def test_build_base_metadata_extra_kwargs() -> None:
    """_build_base_metadata merges extra keyword arguments."""
    import time
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )

    meta: dict[str, Any] = target._build_base_metadata(
        time.monotonic(), error="something broke", custom_key="val",
    )
    assert meta["error"] == "something broke"
    assert meta["custom_key"] == "val"


# ---------------------------------------------------------------------------
# IterableTarget.execute_all success path
# ---------------------------------------------------------------------------

def test_execute_all_returns_one_result_per_item() -> None:
    """execute_all produces one TargetResult per item."""
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/iter"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 2
    assert all(r.success for r in results)


def test_execute_all_builds_correct_paths() -> None:
    """execute_all uses path_for_item to build per-item paths."""
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/iter"

    results: list[TargetResult] = target.execute_all()
    paths: list[str] = [r.data_point.path for r in results]

    assert paths == ["test/iter/a", "test/iter/b"]


def test_execute_all_collects_correct_values() -> None:
    """execute_all collects the value from collect_for_item."""
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/iter"

    results: list[TargetResult] = target.execute_all()
    values: list = [r.data_point.value for r in results]

    assert values == ["value-a", "value-b"]


def test_execute_all_includes_extra_metadata() -> None:
    """execute_all merges extra_metadata_for_item into each result."""
    target: _SimpleIterableTarget = _SimpleIterableTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/iter"

    results: list[TargetResult] = target.execute_all()

    assert results[0].data_point.metadata["item_id"] == "a"
    assert results[1].data_point.metadata["item_id"] == "b"


def test_execute_all_includes_explanation_in_metadata() -> None:
    """execute_all includes explanation in metadata when the target provides one."""
    target: _WithExplanationTarget = _WithExplanationTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/expl"

    results: list[TargetResult] = target.execute_all()

    assert results[0].data_point.metadata["explanation"] == "This checks something important"


# ---------------------------------------------------------------------------
# IterableTarget.execute_all error handling
# ---------------------------------------------------------------------------

def test_execute_all_partial_failure() -> None:
    """execute_all continues when one item fails."""
    target: _FailingItemTarget = _FailingItemTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/fail"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 2
    assert results[0].success is True
    assert results[0].data_point.value == "good"
    assert results[1].success is False
    assert results[1].error == "item failed"
    assert "error" in results[1].data_point.metadata


def test_execute_all_discovery_failure() -> None:
    """execute_all handles get_items() raising an exception."""
    target: _DiscoveryFailsTarget = _DiscoveryFailsTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/disc"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "discovery broken"
    assert results[0].data_point.path == "test/disc"


def test_execute_all_not_applicable_item() -> None:
    """execute_all handles NotApplicableError from collect_for_item."""
    target: _NotApplicableItemTarget = _NotApplicableItemTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/na"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 2

    # First item succeeds
    assert results[0].success is True
    assert results[0].data_point.value == "collected"

    # Second item is not_applicable (still success=True, no scary error)
    assert results[1].success is True
    assert results[1].data_point.metadata.get("not_applicable") is True


def test_execute_all_empty_items() -> None:
    """execute_all returns empty list when get_items() returns empty."""

    class _EmptyTarget(IterableTarget):
        @property
        def description(self) -> str:
            return "empty"

        def get_items(self) -> list:
            return []

        def collect_for_item(self, item: Any) -> str:
            return "never"

        def path_for_item(self, item: Any) -> str:
            return "never"

        def description_for_item(self, item: Any) -> str:
            return "never"

    target: _EmptyTarget = _EmptyTarget(_make_config(), _make_terminal(), _make_logger())
    target._path = "test/empty"

    assert target.execute_all() == []


# ---------------------------------------------------------------------------
# on_none_value hook
# ---------------------------------------------------------------------------

def test_on_none_value_hook_overrides_result() -> None:
    """on_none_value hook can return a custom TargetResult for None values."""
    target: _NoneValueTarget = _NoneValueTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/none"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    # The hook returned success=True with value=None
    assert results[0].success is True
    assert results[0].data_point.value is None


# ---------------------------------------------------------------------------
# PerHostTarget via IterableTarget
# ---------------------------------------------------------------------------

def test_per_host_target_inherits_iterable() -> None:
    """PerHostTarget is a subclass of IterableTarget."""
    assert issubclass(PerHostTarget, IterableTarget)


def test_per_host_target_is_per_host_true() -> None:
    """PerHostTarget.is_per_host returns True for discovery compatibility."""

    class _TestHost(PerHostTarget):
        @property
        def description(self) -> str:
            return "test"

        def get_hosts(self) -> list[dict[str, str]]:
            return [{"name": "h1", "ip": "1.2.3.4"}]

        def collect_for_host(self, host: dict[str, str]) -> str:
            return "ok"

    target: _TestHost = _TestHost(_make_config(), _make_terminal(), _make_logger())
    assert target.is_per_host is True
    assert target.is_iterable is True


# ---------------------------------------------------------------------------
# PerServiceTarget via IterableTarget
# ---------------------------------------------------------------------------

def test_per_service_target_inherits_iterable() -> None:
    """PerServiceTarget is a subclass of IterableTarget."""
    assert issubclass(PerServiceTarget, IterableTarget)


def test_per_service_target_appends_name() -> None:
    """PerServiceTarget appends service name to the base path."""

    class _TestService(PerServiceTarget):
        @property
        def description(self) -> str:
            return "test"

        def get_services(self) -> list[ServiceSpec]:
            return [{"name": "brig", "description": "Brig"}]

        def collect_for_service(self, spec: ServiceSpec) -> str:
            return "healthy"

    target: _TestService = _TestService(_make_config(), _make_terminal(), _make_logger())
    target._path = "wire_services/healthy"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    assert results[0].data_point.path == "wire_services/healthy/brig"
    assert results[0].data_point.metadata["service_name"] == "brig"


# ---------------------------------------------------------------------------
# PerConfigmapTarget via IterableTarget
# ---------------------------------------------------------------------------

def test_per_configmap_target_inherits_iterable() -> None:
    """PerConfigmapTarget is a subclass of IterableTarget."""
    assert issubclass(PerConfigmapTarget, IterableTarget)


def test_per_configmap_target_none_is_not_applicable() -> None:
    """PerConfigmapTarget treats None return as not_applicable."""

    class _TestCM(PerConfigmapTarget):
        @property
        def description(self) -> str:
            return "test"

        def get_configmaps(self) -> list[ConfigmapSpec]:
            return [{
                "name": "brig",
                "configmap_name": "brig",
                "namespace": None,
                "data_key": None,
                "description": "Brig config",
            }]

        def collect_for_configmap(self, spec: ConfigmapSpec) -> str | None:
            return None

    target: _TestCM = _TestCM(_make_config(), _make_terminal(), _make_logger())
    target._path = "config/values"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data_point.value is None
    assert results[0].data_point.metadata.get("not_applicable") is True


# ---------------------------------------------------------------------------
# Skip guards (kubernetes-only mode, admin-host)
# ---------------------------------------------------------------------------

def test_execute_all_skips_ssh_target_in_k8s_only_mode() -> None:
    """execute_all skips SSH-requiring targets when only_through_kubernetes."""
    config = _make_config()
    config.only_through_kubernetes = True

    class _SshTarget(IterableTarget):
        requires_ssh = True

        @property
        def description(self) -> str:
            return "ssh target"

        def get_items(self) -> list:
            return [{"id": "x"}]

        def collect_for_item(self, item: Any) -> str:
            return "should not run"

        def path_for_item(self, item: Any) -> str:
            return "test/ssh"

        def description_for_item(self, item: Any) -> str:
            return "ssh"

    target: _SshTarget = _SshTarget(config, _make_terminal(), _make_logger())
    target._path = "test/ssh"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data_point.metadata.get("not_applicable") is True
    assert "SSH" in results[0].data_point.metadata.get("not_applicable_reason", "")


# ---------------------------------------------------------------------------
# Path construction helpers
# ---------------------------------------------------------------------------

def test_build_path_insert_multi_segment() -> None:
    """build_path_insert inserts item name between prefix and filename."""
    assert build_path_insert("vm/disk_usage", "kubenode1") == "vm/kubenode1/disk_usage"


def test_build_path_insert_deep_path() -> None:
    """build_path_insert splits on the last slash only."""
    assert build_path_insert("check/deep/nested", "host1") == "check/deep/host1/nested"


def test_build_path_insert_single_segment() -> None:
    """build_path_insert prepends item name for single-segment paths."""
    assert build_path_insert("status", "node1") == "node1/status"


def test_build_path_append_multi_segment() -> None:
    """build_path_append appends item name to the end."""
    assert build_path_append("wire_services/healthy", "brig") == "wire_services/healthy/brig"


def test_build_path_append_single_segment() -> None:
    """build_path_append works with single-segment base paths too."""
    assert build_path_append("config", "brig") == "config/brig"
