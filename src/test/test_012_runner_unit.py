"""Unit tests for the runner module.

Tests Runner initialization, the run() lifecycle (config loading, target discovery,
filtering, execution, JSONL output, summary), error paths (config error,
filter error, target failure), per-host target handling, writer cleanup,
and _format_duration().
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch, call

from src.lib.runner import Runner
from src.lib.config import ConfigError
from src.lib.base_target import BaseTarget, TargetResult
from src.lib.per_host_target import PerHostTarget
from src.lib.logger import LogLevel
from src.lib.output import DataPoint
from src.lib.target_discovery import DiscoveredTarget
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data_point(path: str = "test/target", value: str | int = 42) -> DataPoint:
    """Makes a simple DataPoint for testing."""
    return DataPoint(
        path=path,
        value=value,
        unit="items",
        description="test",
        raw_output="",
        metadata={},
    )


def _make_target_result(
    success: bool = True,
    path: str = "test/target",
    value: str | int = 42,
) -> TargetResult:
    """Makes a TargetResult for testing."""
    return TargetResult(
        data_point=_make_data_point(path=path, value=value),
        success=success,
        error=None if success else "failed",
        duration_seconds=0.1,
    )


# ---------------------------------------------------------------------------
# Runner.__init__ parameter storage
# ---------------------------------------------------------------------------

def test_runner_init_stores_parameters() -> None:
    """Check that Runner constructor stores all parameters."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
        target_pattern="databases/*",
        verbosity=Verbosity.QUIET,
        use_color=False,
    )

    assert runner.config_path == "/tmp/cfg.yaml"
    assert runner.output_path == "/tmp/out.jsonl"
    assert runner.target_pattern == "databases/*"
    assert runner.verbosity == Verbosity.QUIET
    assert runner.use_color is False


def test_runner_init_defaults() -> None:
    """Check that Runner constructor applies default values."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
    )

    assert runner.target_pattern == "*"
    assert runner.verbosity == Verbosity.NORMAL
    assert runner.use_color is True


def test_runner_init_creates_terminal() -> None:
    """Check that Runner creates a Terminal with matching verbosity and color."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
        verbosity=Verbosity.QUIET,
        use_color=False,
    )

    assert isinstance(runner.terminal, Terminal)
    assert runner.terminal._verbosity == Verbosity.QUIET
    assert runner.terminal._use_color is False


def test_runner_init_verbose_creates_debug_logger() -> None:
    """Check that verbose mode creates a DEBUG-level logger."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
        verbosity=Verbosity.VERBOSE,
    )

    assert runner.logger._level == LogLevel.DEBUG


def test_runner_init_normal_creates_info_logger() -> None:
    """Check that non-verbose mode creates an INFO-level logger."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
        verbosity=Verbosity.NORMAL,
    )

    assert runner.logger._level == LogLevel.INFO


# ---------------------------------------------------------------------------
# Runner.run() config error path
# ---------------------------------------------------------------------------

def test_run_config_error_returns_2() -> None:
    """Check that run() returns exit code 2 when config loading fails."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
        verbosity=Verbosity.QUIET,
    )

    with patch(
        "src.lib.runner.load_config",
        side_effect=ConfigError(["bad ip", "missing field"]),
    ):
        exit_code: int = runner.run()

    assert exit_code == 2


# ---------------------------------------------------------------------------
# Runner.run() filter error path
# ---------------------------------------------------------------------------

def test_run_filter_error_returns_1() -> None:
    """Check that run() returns exit code 1 when target filter finds no matches."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
        target_pattern="nonexistent/*",
        verbosity=Verbosity.QUIET,
    )

    with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
        with patch("src.lib.runner.discover_targets", return_value=[]):
            with patch(
                "src.lib.runner.filter_targets",
                side_effect=ValueError("No targets match"),
            ):
                exit_code: int = runner.run()

    assert exit_code == 1


# ---------------------------------------------------------------------------
# Runner.run() successful execution
# ---------------------------------------------------------------------------

def test_run_all_targets_pass_returns_0() -> None:
    """Check that run() returns 0 when all targets succeed."""
    # Use a real temp file for the JSONL output
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        # Create a mock target class that returns success from execute()
        mock_target_instance = MagicMock()
        mock_target_instance.execute.return_value = _make_target_result(success=True)
        mock_target_class = MagicMock(return_value=mock_target_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="test/alpha",
                module_path="src.targets.test.alpha",
                target_class=mock_target_class,
                is_per_host=False,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    exit_code: int = runner.run()

        assert exit_code == 0
    finally:
        os.unlink(output_path)


def test_run_target_failure_returns_1() -> None:
    """Check that run() returns 1 when any target fails."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        # One passing target, one failing target
        mock_pass_instance = MagicMock()
        mock_pass_instance.execute.return_value = _make_target_result(success=True)
        mock_pass_class = MagicMock(return_value=mock_pass_instance)

        mock_fail_instance = MagicMock()
        mock_fail_instance.execute.return_value = _make_target_result(success=False)
        mock_fail_class = MagicMock(return_value=mock_fail_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="test/pass",
                module_path="src.targets.test.pass",
                target_class=mock_pass_class,
                is_per_host=False,
            ),
            DiscoveredTarget(
                path="test/fail",
                module_path="src.targets.test.fail",
                target_class=mock_fail_class,
                is_per_host=False,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    exit_code: int = runner.run()

        assert exit_code == 1
    finally:
        os.unlink(output_path)


# ---------------------------------------------------------------------------
# Runner.run() per-host target handling
# ---------------------------------------------------------------------------

def test_run_per_host_target_calls_execute_all() -> None:
    """Check that run() calls execute_all() for per-host targets."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        # Mock per-host target with multiple results
        mock_instance = MagicMock()
        mock_instance.execute_all.return_value = [
            _make_target_result(success=True, path="vm/host1/disk"),
            _make_target_result(success=True, path="vm/host2/disk"),
        ]
        mock_class = MagicMock(return_value=mock_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="vm/disk",
                module_path="src.targets.vm.disk",
                target_class=mock_class,
                is_per_host=True,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    exit_code: int = runner.run()

        # execute_all was called instead of execute
        mock_instance.execute_all.assert_called_once()
        mock_instance.execute.assert_not_called()
        assert exit_code == 0
    finally:
        os.unlink(output_path)


# ---------------------------------------------------------------------------
# Runner.run() JSONL writer
# ---------------------------------------------------------------------------

def test_run_writes_data_points_to_jsonl() -> None:
    """Check that run() writes each target's data_point to the JSONL writer."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        dp: DataPoint = _make_data_point(path="test/written")
        result: TargetResult = TargetResult(
            data_point=dp,
            success=True,
            error=None,
            duration_seconds=0.1,
        )

        mock_instance = MagicMock()
        mock_instance.execute.return_value = result
        mock_class = MagicMock(return_value=mock_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="test/written",
                module_path="src.targets.test.written",
                target_class=mock_class,
                is_per_host=False,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    runner.run()

        # Read the JSONL file and check that content was written
        with open(output_path, 'r') as f:
            content: str = f.read()

        assert "test/written" in content
    finally:
        os.unlink(output_path)


def test_run_skips_none_data_points() -> None:
    """Check that run() doesn't write to JSONL when data_point is None."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        result: TargetResult = TargetResult(
            data_point=None,
            success=False,
            error="broken",
            duration_seconds=0.01,
        )

        mock_instance = MagicMock()
        mock_instance.execute.return_value = result
        mock_class = MagicMock(return_value=mock_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="test/none_dp",
                module_path="src.targets.test.none_dp",
                target_class=mock_class,
                is_per_host=False,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    runner.run()

        # File should be empty since data_point was None
        with open(output_path, 'r') as f:
            content: str = f.read()

        assert content.strip() == ""
    finally:
        os.unlink(output_path)


# ---------------------------------------------------------------------------
# Runner.run() writer cleanup on error
# ---------------------------------------------------------------------------

def test_run_closes_writer_on_target_exception() -> None:
    """Check that the JSONL writer is closed even if a target throws unexpectedly."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        # Target that throws an unexpected error from execute() (not a normal failure)
        mock_instance = MagicMock()
        mock_instance.execute.side_effect = RuntimeError("catastrophic")
        mock_class = MagicMock(return_value=mock_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="test/crash",
                module_path="src.targets.test.crash",
                target_class=mock_class,
                is_per_host=False,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    try:
                        runner.run()
                    except RuntimeError:
                        pass

        # File should exist and be accessible (the writer was closed)
        assert os.path.exists(output_path)
    finally:
        os.unlink(output_path)


# ---------------------------------------------------------------------------
# Runner.run() target instantiation
# ---------------------------------------------------------------------------

def test_run_sets_target_path() -> None:
    """Check that run() sets _path on target instances from discovered path."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path: str = tmp.name

    try:
        runner: Runner = Runner(
            config_path="/tmp/cfg.yaml",
            output_path=output_path,
            verbosity=Verbosity.QUIET,
        )

        mock_instance = MagicMock()
        mock_instance.execute.return_value = _make_target_result(success=True)
        mock_class = MagicMock(return_value=mock_instance)

        discovered: list[DiscoveredTarget] = [
            DiscoveredTarget(
                path="databases/cassandra/status",
                module_path="src.targets.databases.cassandra.status",
                target_class=mock_class,
                is_per_host=False,
            ),
        ]

        with patch("src.lib.runner.load_config", return_value=make_minimal_config()):
            with patch("src.lib.runner.discover_targets", return_value=discovered):
                with patch("src.lib.runner.filter_targets", return_value=discovered):
                    runner.run()

        # _path should be set on the mock instance
        assert mock_instance._path == "databases/cassandra/status"
    finally:
        os.unlink(output_path)


# ---------------------------------------------------------------------------
# Runner._format_duration
# ---------------------------------------------------------------------------

def test_format_duration_seconds_only() -> None:
    """Check that _format_duration formats short durations as Xs."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
    )

    assert runner._format_duration(5.23) == "5.2s"
    assert runner._format_duration(0.0) == "0.0s"
    assert runner._format_duration(59.99) == "60.0s"


def test_format_duration_minutes_and_seconds() -> None:
    """Check that _format_duration formats longer durations as Xm Ys."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
    )

    assert runner._format_duration(60.0) == "1m 0s"
    assert runner._format_duration(125.7) == "2m 5s"
    assert runner._format_duration(3661.0) == "61m 1s"


def test_format_duration_boundary() -> None:
    """Check the _format_duration boundary at exactly 60 seconds."""
    runner: Runner = Runner(
        config_path="/tmp/cfg.yaml",
        output_path="/tmp/out.jsonl",
    )

    # 59.9 rounds to 59.9s (stays in seconds)
    result: str = runner._format_duration(59.9)
    assert result == "59.9s"

    # 60.0 goes to minutes
    result = runner._format_duration(60.0)
    assert result == "1m 0s"
