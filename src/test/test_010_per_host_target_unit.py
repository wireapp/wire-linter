"""Unit tests for the per_host_target module.

Tests PerHostTarget lifecycle (execute_all), how paths get built per-host,
per-host accumulator resets, error handling, and description methods.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget, TargetResult
from src.lib.config import Config
from src.lib.logger import Logger, LogLevel
from src.lib.output import DataPoint
from src.lib.per_host_target import PerHostTarget
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Delegate to the single authoritative helper so field additions only need
# updating in one place (conftest.py), not in every test file.
_make_config = make_minimal_config


def _make_terminal() -> Terminal:
    """Make a quiet terminal so tests don't get drowned in noise.

    Args:
        (none)

    Returns:
        A Terminal set to QUIET verbosity with no color.
    """
    # QUIET mode keeps test output clean and readable.
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Make a logger that shuts up during tests.

    Args:
        (none)

    Returns:
        A Logger set to ERROR level, so only real problems show up.
    """
    # ERROR level = only critical stuff surfaces, debug/info chatter stays hidden.
    return Logger(level=LogLevel.ERROR)


# Shared sample hosts for multiple test targets to keep test data consistent.
SAMPLE_HOSTS: list[dict[str, str]] = [
    {"name": "kubenode1", "ip": "192.168.1.10"},
    {"name": "kubenode2", "ip": "192.168.1.11"},
]


class _DiskUsageTarget(PerHostTarget):
    """Concrete per-host target that returns a value per host."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Disk usage"

    @property
    def unit(self) -> str:
        """Return the unit for measured values."""
        return "%"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return the list of hosts to check."""
        return SAMPLE_HOSTS

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Return a fake disk-usage percentage per host."""
        # Different values per host so we can verify per-host isolation works.
        if host["name"] == "kubenode1":
            return 45
        return 72


class _FailingHostTarget(PerHostTarget):
    """Per-host target where one host fails."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Failing host check"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return the list of hosts to check."""
        return SAMPLE_HOSTS

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Blow up on the second host to test failure handling."""
        if host["name"] == "kubenode2":
            raise RuntimeError("SSH connection refused")
        return "ok"


class _AllFailTarget(PerHostTarget):
    """Per-host target where all hosts fail."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "All fail check"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return the list of hosts to check."""
        return SAMPLE_HOSTS

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Always blow up to simulate total failure."""
        raise RuntimeError(f"Failed on {host['name']}")


class _SingleHostTarget(PerHostTarget):
    """Per-host target with a single host."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Single host"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return just one host for testing."""
        return [{"name": "solo", "ip": "10.0.0.50"}]

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Return a fixed status value."""
        return "running"


class _EmptyHostsTarget(PerHostTarget):
    """Per-host target with no hosts."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Empty hosts"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return an empty list, like there's no hosts."""
        return []

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Never called because get_hosts returns empty list."""
        return None


class _CustomDescriptionTarget(PerHostTarget):
    """Per-host target with custom description_for_host."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Custom desc"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return a single host to test custom descriptions."""
        return [{"name": "host1", "ip": "10.0.0.1"}]

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Return a fixed value."""
        return 99

    def description_for_host(self, host: dict[str, str]) -> str:
        """Return a custom description with the host name in it."""
        return f"Custom check for {host['name']}"


class _SingleSegmentPathTarget(PerHostTarget):
    """Per-host target with a single-segment path (no '/' in _path)."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Single segment"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return a single host to test path building."""
        return [{"name": "node1", "ip": "10.0.0.5"}]

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Return a fixed value."""
        return "single"


class _DescriptionFailsTarget(PerHostTarget):
    """Per-host target where description_for_host raises during error path."""

    @property
    def description(self) -> str:
        """Return a human-readable description of this target."""
        return "Desc fails"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return a single host to test fallback when description blows up."""
        return [{"name": "node1", "ip": "10.0.0.1"}]

    def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
        """Always fail to trigger the error path."""
        raise RuntimeError("collect failed")

    def description_for_host(self, host: dict[str, str]) -> str:
        """Always blow up to test fallback when description fails."""
        raise ValueError("description also failed")


# ---------------------------------------------------------------------------
# PerHostTarget is_per_host marker
# ---------------------------------------------------------------------------

def test_is_per_host_property() -> None:
    """Check that PerHostTarget.is_per_host returns True.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )

    # Runner uses is_per_host to decide between execute() and execute_all().
    assert target.is_per_host is True


# ---------------------------------------------------------------------------
# PerHostTarget get_hosts / collect_for_host not implemented
# ---------------------------------------------------------------------------

def test_get_hosts_not_implemented() -> None:
    """Check that base PerHostTarget.get_hosts raises NotImplementedError.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    try:
        # Calling the base class directly should force subclasses to implement get_hosts.
        PerHostTarget(_make_config(), _make_terminal(), _make_logger()).get_hosts()
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        pass


def test_collect_for_host_not_implemented() -> None:
    """Check that base PerHostTarget.collect_for_host raises NotImplementedError.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    try:
        # Calling the base class directly should force subclasses to implement collect_for_host.
        PerHostTarget(_make_config(), _make_terminal(), _make_logger()).collect_for_host(
            {"name": "x", "ip": "1.2.3.4"}
        )
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        pass


# ---------------------------------------------------------------------------
# PerHostTarget default description_for_host
# ---------------------------------------------------------------------------

def test_default_description_for_host() -> None:
    """Check that default description_for_host adds host name and IP.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    host: dict[str, str] = {"name": "kubenode1", "ip": "192.168.1.10"}

    desc: str = target.description_for_host(host)

    # Default format includes base description, host name, and IP.
    assert desc == "Disk usage on kubenode1 (192.168.1.10)"


# ---------------------------------------------------------------------------
# PerHostTarget execute_all success
# ---------------------------------------------------------------------------

def test_execute_all_returns_one_result_per_host() -> None:
    """Check that execute_all returns one TargetResult per host.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "vm/disk_usage"

    results: list[TargetResult] = target.execute_all()

    # One result per host, all successful.
    assert len(results) == 2
    assert all(r.success is True for r in results)


def test_execute_all_per_host_paths() -> None:
    """Check that execute_all builds per-host paths the right way.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "vm/disk_usage"

    results: list[TargetResult] = target.execute_all()
    paths: list[str] = [r.data_point.path for r in results]

    # Path format is {prefix}/{host_name}/{filename}.
    assert paths[0] == "vm/kubenode1/disk_usage"
    assert paths[1] == "vm/kubenode2/disk_usage"


def test_execute_all_per_host_values() -> None:
    """Check that execute_all grabs different values per host.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "vm/disk_usage"

    results: list[TargetResult] = target.execute_all()

    # Each host's value should match what collect_for_host returned.
    assert results[0].data_point.value == 45
    assert results[1].data_point.value == 72


def test_execute_all_metadata_includes_host_info() -> None:
    """Check that metadata includes host_name and host_ip in results.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "vm/disk_usage"

    results: list[TargetResult] = target.execute_all()

    # Metadata should identify the host so consumers know which result is which.
    assert results[0].data_point.metadata["host_name"] == "kubenode1"
    assert results[0].data_point.metadata["host_ip"] == "192.168.1.10"
    assert results[1].data_point.metadata["host_name"] == "kubenode2"
    assert results[1].data_point.metadata["host_ip"] == "192.168.1.11"


def test_execute_all_unit_propagated() -> None:
    """Check that the target's unit gets set on every DataPoint.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DiskUsageTarget = _DiskUsageTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "vm/disk_usage"

    results: list[TargetResult] = target.execute_all()

    # Unit should show up on every result so the UI can label them right.
    assert all(r.data_point.unit == "%" for r in results)


# ---------------------------------------------------------------------------
# PerHostTarget execute_all with single-segment path
# ---------------------------------------------------------------------------

def test_execute_all_single_segment_path() -> None:
    """Check path building when the base path has no «/» in it.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _SingleSegmentPathTarget = _SingleSegmentPathTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "status"

    results: list[TargetResult] = target.execute_all()

    # With no directory prefix, path is {host_name}/{filename}.
    assert results[0].data_point.path == "node1/status"


# ---------------------------------------------------------------------------
# PerHostTarget execute_all partial failure
# ---------------------------------------------------------------------------

def test_execute_all_partial_failure() -> None:
    """Check that execute_all keeps going when one host fails.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _FailingHostTarget = _FailingHostTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "check/health"

    results: list[TargetResult] = target.execute_all()

    # Both hosts should produce a result, not stop on failure.
    assert len(results) == 2

    # First host succeeds.
    assert results[0].success is True
    assert results[0].data_point.value == "ok"

    # Second host fails with the right error message.
    assert results[1].success is False
    assert results[1].error == "SSH connection refused"
    assert results[1].data_point.value is None
    assert "error" in results[1].data_point.metadata


def test_execute_all_failure_metadata() -> None:
    """Check that failed results still have host_name and host_ip in metadata.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _FailingHostTarget = _FailingHostTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "check/health"

    results: list[TargetResult] = target.execute_all()
    failed_meta: dict = results[1].data_point.metadata

    # Even on failure, metadata should have host identity for debugging.
    assert failed_meta["host_name"] == "kubenode2"
    assert failed_meta["host_ip"] == "192.168.1.11"
    assert failed_meta["error"] == "SSH connection refused"


# ---------------------------------------------------------------------------
# PerHostTarget execute_all all failures
# ---------------------------------------------------------------------------

def test_execute_all_all_failures() -> None:
    """Check that execute_all handles all hosts failing.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _AllFailTarget = _AllFailTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "check/fail"

    results: list[TargetResult] = target.execute_all()

    # All hosts should produce failed results instead of blowing up execute_all.
    assert len(results) == 2
    assert all(r.success is False for r in results)
    assert "kubenode1" in results[0].error
    assert "kubenode2" in results[1].error


# ---------------------------------------------------------------------------
# PerHostTarget execute_all empty hosts
# ---------------------------------------------------------------------------

def test_execute_all_empty_hosts() -> None:
    """Check that execute_all returns empty list when there's no hosts.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _EmptyHostsTarget = _EmptyHostsTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "check/empty"

    results: list[TargetResult] = target.execute_all()

    # No hosts, no results... caller needs to handle it gracefully.
    assert results == []


# ---------------------------------------------------------------------------
# PerHostTarget execute_all single host
# ---------------------------------------------------------------------------

def test_execute_all_single_host() -> None:
    """Check that execute_all works with just one host.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _SingleHostTarget = _SingleHostTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "service/status"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].data_point.path == "service/solo/status"
    assert results[0].data_point.value == "running"


# ---------------------------------------------------------------------------
# PerHostTarget custom description_for_host
# ---------------------------------------------------------------------------

def test_execute_all_custom_description() -> None:
    """Check that execute_all uses the custom description_for_host.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _CustomDescriptionTarget = _CustomDescriptionTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "custom/check"

    results: list[TargetResult] = target.execute_all()

    # The overridden description_for_host should supply the DataPoint description.
    assert results[0].data_point.description == "Custom check for host1"


# ---------------------------------------------------------------------------
# PerHostTarget description_for_host fallback on error
# ---------------------------------------------------------------------------

def test_execute_all_description_failure_fallback() -> None:
    """Check that execute_all handles description_for_host blowing up during errors.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """
    target: _DescriptionFailsTarget = _DescriptionFailsTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "broken/desc"

    results: list[TargetResult] = target.execute_all()

    assert len(results) == 1
    assert results[0].success is False

    # When description_for_host blows up during the error path, we fall back to
    # an empty string instead of throwing another exception.
    assert results[0].data_point.description == ""


# ---------------------------------------------------------------------------
# PerHostTarget accumulators reset per host
# ---------------------------------------------------------------------------

def test_execute_all_accumulators_reset_per_host() -> None:
    """Check that _raw_outputs and _commands_run reset between hosts.

    Args:
        (none)

    Returns:
        None raises AssertionError on failure.
    """

    class _OutputTrackingTarget(PerHostTarget):
        @property
        def description(self) -> str:
            """Return a human-readable description of this target."""
            return "Output tracking"

        def get_hosts(self) -> list[dict[str, str]]:
            """Return the shared SAMPLE_HOSTS list."""
            return SAMPLE_HOSTS

        def collect_for_host(self, host: dict[str, str]) -> str | int | float | bool | None:
            """Track one output entry per host and return the host name."""
            # Call _track_output so we can verify isolation between hosts.
            self._track_output(f"cmd-{host['name']}", f"output-{host['name']}")
            return host["name"]

    target: _OutputTrackingTarget = _OutputTrackingTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "track/output"

    results: list[TargetResult] = target.execute_all()

    # Each result's raw_output should have only that host's output, so we know
    # the accumulator gets cleared between iterations.
    assert "output-kubenode1" in results[0].data_point.raw_output
    assert "output-kubenode2" not in results[0].data_point.raw_output

    assert "output-kubenode2" in results[1].data_point.raw_output
    assert "output-kubenode1" not in results[1].data_point.raw_output
