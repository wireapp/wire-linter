"""Unit tests for the base_target module.

Tests the TargetResult dataclass, BaseTarget lifecycle (execute), command helper
tracking, error handling, dynamic descriptions, and helper methods. Everything's
mocked so we can test behavior in isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.lib.base_target import BaseTarget, TargetResult
from src.lib.command import CommandResult
from src.lib.config import Config
from src.lib.http_client import HttpResult
from src.lib.logger import Logger, LogLevel
from src.lib.output import DataPoint
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Delegate to the single authoritative helper so field additions only need
# updating in one place (conftest.py), not in every test file.
_make_config = make_minimal_config


def _make_terminal() -> Terminal:
    """Creates a quiet terminal so tests don't spam output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Creates a logger that shuts up unless it's an error."""
    return Logger(level=LogLevel.ERROR)


class _SimpleTarget(BaseTarget):
    """Concrete target that returns a fixed value."""

    @property
    def description(self) -> str:
        return "Simple test target"

    @property
    def unit(self) -> str:
        return "items"

    def collect(self) -> str | int | float | bool | None:
        return 42


class _FailingTarget(BaseTarget):
    """Concrete target that raises during collect()."""

    @property
    def description(self) -> str:
        return "Failing target"

    def collect(self) -> str | int | float | bool | None:
        raise RuntimeError("collection failed")


class _DynamicDescTarget(BaseTarget):
    """Concrete target that sets a dynamic description during collect()."""

    @property
    def description(self) -> str:
        return "Static description"

    def collect(self) -> str | int | float | bool | None:
        self._dynamic_description = "Dynamic description override"
        return "ok"


class _DescriptionRaisesTarget(BaseTarget):
    """Target whose description property raises, AND collect() also raises."""

    @property
    def description(self) -> str:
        raise ValueError("description broken")

    def collect(self) -> str | int | float | bool | None:
        raise RuntimeError("collect also failed")


class _TrackingTarget(BaseTarget):
    """Target that exercises command helpers with mocked dependencies."""

    @property
    def description(self) -> str:
        return "Tracking target"

    def collect(self) -> str | int | float | bool | None:
        # These will be called with mocked underlying functions
        return "tracked"


# ---------------------------------------------------------------------------
# TargetResult dataclass fields
# ---------------------------------------------------------------------------

def test_target_result_fields() -> None:
    """TargetResult should hold all the fields we give it."""
    dp: DataPoint = DataPoint(
        path="test/path",
        value=42,
        unit="items",
        description="desc",
        raw_output="raw",
        metadata={},
    )
    result: TargetResult = TargetResult(
        data_point=dp,
        success=True,
        error=None,
        duration_seconds=1.5,
    )

    assert result.data_point is dp
    assert result.success is True
    assert result.error is None
    assert result.duration_seconds == 1.5


def test_target_result_failure() -> None:
    """TargetResult handles failure cases with no data_point."""
    result: TargetResult = TargetResult(
        data_point=None,
        success=False,
        error="something broke",
        duration_seconds=0.1,
    )

    assert result.data_point is None
    assert result.success is False
    assert result.error == "something broke"


# ---------------------------------------------------------------------------
# BaseTarget constructor and properties
# ---------------------------------------------------------------------------

def test_base_target_init() -> None:
    """BaseTarget constructor stashes config, terminal, logger, and sets up accumulators."""
    config: Config = _make_config()
    terminal: Terminal = _make_terminal()
    logger: Logger = _make_logger()
    target: _SimpleTarget = _SimpleTarget(config, terminal, logger)

    assert target.config is config
    assert target.terminal is terminal
    assert target.logger is logger
    assert target.path == ""
    assert target._raw_outputs == []
    assert target._commands_run == []


def test_base_target_path_property() -> None:
    """path property returns what the discovery system sets."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())
    target._path = "databases/cassandra/status"

    assert target.path == "databases/cassandra/status"


def test_base_target_description_not_implemented() -> None:
    """Base class description is abstract and blows up if you try to call it."""
    try:
        _ = BaseTarget(_make_config(), _make_terminal(), _make_logger()).description
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        pass


def test_base_target_collect_not_implemented() -> None:
    """Base class collect() is abstract and throws NotImplementedError."""
    try:
        BaseTarget(_make_config(), _make_terminal(), _make_logger()).collect()
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        pass


def test_base_target_default_unit() -> None:
    """unit defaults to empty string if not overridden."""

    class _NoUnitTarget(BaseTarget):
        @property
        def description(self) -> str:
            return "no unit"

        def collect(self) -> str | int | float | bool | None:
            return 1

    target: _NoUnitTarget = _NoUnitTarget(_make_config(), _make_terminal(), _make_logger())

    assert target.unit == ""


# ---------------------------------------------------------------------------
# BaseTarget execute() success path
# ---------------------------------------------------------------------------

def test_execute_success_returns_target_result() -> None:
    """execute() returns a TargetResult with the right DataPoint on success."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())
    target._path = "test/simple"

    result: TargetResult = target.execute()

    assert result.success is True
    assert result.error is None
    assert result.duration_seconds >= 0
    assert result.data_point is not None
    assert result.data_point.path == "test/simple"
    assert result.data_point.value == 42
    assert result.data_point.unit == "items"
    assert result.data_point.description == "Simple test target"


def test_execute_success_metadata() -> None:
    """metadata includes collected_at, commands, and duration_seconds."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())
    target._path = "test/meta"

    result: TargetResult = target.execute()
    meta: dict = result.data_point.metadata

    assert "collected_at" in meta, f"Missing collected_at in metadata: {meta}"
    assert "commands" in meta, f"Missing commands in metadata: {meta}"
    assert "duration_seconds" in meta, f"Missing duration_seconds in metadata: {meta}"
    assert isinstance(meta["commands"], list)
    assert isinstance(meta["duration_seconds"], float)


def test_execute_resets_accumulators() -> None:
    """execute() clears old state before running collect()."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())
    target._path = "test/reset"

    # throw some junk in the accumulators to see if it gets cleaned up
    target._raw_outputs = ["leftover"]
    target._commands_run = ["old command"]
    target._dynamic_description = "old dynamic"

    result: TargetResult = target.execute()

    # everything should be fresh after execute() runs
    assert result.success is True
    assert result.data_point.raw_output == ""
    assert result.data_point.metadata["commands"] == []
    assert result.data_point.description == "Simple test target"


# ---------------------------------------------------------------------------
# BaseTarget execute() failure path
# ---------------------------------------------------------------------------

def test_execute_failure_returns_error_result() -> None:
    """execute() catches exceptions and wraps them in a TargetResult."""
    target: _FailingTarget = _FailingTarget(_make_config(), _make_terminal(), _make_logger())
    target._path = "test/failing"

    result: TargetResult = target.execute()

    assert result.success is False
    assert result.error == "collection failed"
    assert result.duration_seconds >= 0
    assert result.data_point is not None
    assert result.data_point.path == "test/failing"
    assert result.data_point.value is None
    assert result.data_point.description == "Failing target"
    assert "error" in result.data_point.metadata
    assert result.data_point.metadata["error"] == "collection failed"


def test_execute_failure_description_fallback() -> None:
    """execute() doesn't choke if description itself blows up."""
    target: _DescriptionRaisesTarget = _DescriptionRaisesTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/desc_raises"

    result: TargetResult = target.execute()

    assert result.success is False
    assert result.error == "collect also failed"
    # if both description and dynamic fail, we just use empty string
    assert result.data_point.description == ""


# ---------------------------------------------------------------------------
# BaseTarget dynamic description
# ---------------------------------------------------------------------------

def test_execute_uses_dynamic_description() -> None:
    """execute() uses _dynamic_description if it's set."""
    target: _DynamicDescTarget = _DynamicDescTarget(
        _make_config(), _make_terminal(), _make_logger()
    )
    target._path = "test/dynamic"

    result: TargetResult = target.execute()

    assert result.success is True
    assert result.data_point.description == "Dynamic description override"


# ---------------------------------------------------------------------------
# BaseTarget _track_output
# ---------------------------------------------------------------------------

def test_track_output_appends_nonempty() -> None:
    """_track_output adds output and command to their respective lists."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    target._track_output("echo hello", "hello\n")

    assert "hello\n" in target._raw_outputs
    assert "echo hello" in target._commands_run


def test_track_output_skips_empty_stdout() -> None:
    """_track_output ignores empty or whitespace-only output."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    target._track_output("echo", "   \n  ")

    # command still gets tracked, but the empty output gets dropped
    assert target._raw_outputs == []
    assert "echo" in target._commands_run


def test_track_output_always_tracks_command() -> None:
    """_track_output records every command, even if the output is empty."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    target._track_output("cmd1", "output1")
    target._track_output("cmd2", "")
    target._track_output("cmd3", "output3")

    assert target._commands_run == ["cmd1", "cmd2", "cmd3"]
    assert len(target._raw_outputs) == 2


# ---------------------------------------------------------------------------
# BaseTarget run_local helper
# ---------------------------------------------------------------------------

def test_run_local_calls_run_command() -> None:
    """run_local calls run_command and keeps track of the output."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: CommandResult = CommandResult(
        command="echo test",
        exit_code=0,
        stdout="test output\n",
        stderr="",
        duration_seconds=0.01,
        success=True,
        timed_out=False,
    )

    with patch("src.lib.base_target.run_command", return_value=mock_result) as mock_cmd:
        result: CommandResult = target.run_local(["echo", "test"])

        mock_cmd.assert_called_once_with(["echo", "test"], timeout=30)
        assert result is mock_result
        assert "test output\n" in target._raw_outputs
        assert "echo test" in target._commands_run


def test_run_local_uses_custom_timeout() -> None:
    """run_local respects custom timeout values."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: CommandResult = CommandResult(
        command="sleep 1",
        exit_code=0, stdout="", stderr="",
        duration_seconds=0.01, success=True, timed_out=False,
    )

    with patch("src.lib.base_target.run_command", return_value=mock_result) as mock_cmd:
        target.run_local(["sleep", "1"], timeout=60)

        mock_cmd.assert_called_once_with(["sleep", "1"], timeout=60)


# ---------------------------------------------------------------------------
# BaseTarget run_ssh helper
# ---------------------------------------------------------------------------

def test_run_ssh_calls_run_ssh_command() -> None:
    """run_ssh uses the ssh builder to execute commands on a remote host."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: CommandResult = CommandResult(
        command="ssh deploy@10.0.0.5 uptime",
        exit_code=0, stdout="up 10 days\n", stderr="",
        duration_seconds=0.5, success=True, timed_out=False,
    )

    # mock the ssh chain: ssh.to(host).run(command) -> result
    mock_ssh_target: MagicMock = MagicMock()
    mock_ssh_target.run.return_value = mock_result

    with patch.object(target, 'ssh') as mock_ssh:
        mock_ssh.to.return_value = mock_ssh_target

        result: CommandResult = target.run_ssh("10.0.0.5", "uptime")

        # no ssh_key in config, so we just use ssh.to(host).run(command)
        mock_ssh.to.assert_called_once_with("10.0.0.5")
        mock_ssh_target.run.assert_called_once_with("uptime")
        assert result is mock_result
        assert "up 10 days\n" in target._raw_outputs
        assert "ssh 10.0.0.5 uptime" in target._commands_run


# ---------------------------------------------------------------------------
# BaseTarget run_kubectl helper
# ---------------------------------------------------------------------------

def test_run_kubectl_delegates_to_kubectl_get() -> None:
    """run_kubectl calls kubectl_get with the right namespace."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_cmd_result: CommandResult = CommandResult(
        command="kubectl get nodes -o json",
        exit_code=0, stdout='{"items": []}', stderr="",
        duration_seconds=0.3, success=True, timed_out=False,
    )
    parsed: dict = {"items": []}

    with patch("src.lib.base_target.kubectl_get", return_value=(mock_cmd_result, parsed)) as mock_kube:
        result_cmd, result_parsed = target.run_kubectl("nodes")

        mock_kube.assert_called_once()
        call_kwargs = mock_kube.call_args[1]
        assert call_kwargs["resource"] == "nodes"
        assert call_kwargs["namespace"] == "wire"
        assert call_kwargs["selector"] is None
        assert call_kwargs["all_namespaces"] == False
        assert call_kwargs["timeout"] == 30
        assert call_kwargs["context"] == ""
        assert result_cmd is mock_cmd_result
        assert result_parsed is parsed


def test_run_kubectl_with_explicit_namespace() -> None:
    """run_kubectl respects the namespace you pass instead of using config defaults."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_cmd_result: CommandResult = CommandResult(
        command="kubectl get pods -o json -n kube-system",
        exit_code=0, stdout='{}', stderr="",
        duration_seconds=0.1, success=True, timed_out=False,
    )

    with patch("src.lib.base_target.kubectl_get", return_value=(mock_cmd_result, {})) as mock_kube:
        target.run_kubectl("pods", namespace="kube-system")

        mock_kube.assert_called_once()
        call_kwargs = mock_kube.call_args[1]
        assert call_kwargs["namespace"] == "kube-system"


# ---------------------------------------------------------------------------
# BaseTarget run_kubectl_raw helper
# ---------------------------------------------------------------------------

def test_run_kubectl_raw_delegates_to_kubectl_raw() -> None:
    """run_kubectl_raw delegates to kubectl_raw and stores the output."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: CommandResult = CommandResult(
        command="kubectl top nodes",
        exit_code=0, stdout="NAME  CPU  MEM\n", stderr="",
        duration_seconds=0.2, success=True, timed_out=False,
    )

    with patch("src.lib.base_target.kubectl_raw", return_value=mock_result) as mock_raw:
        result: CommandResult = target.run_kubectl_raw(["top", "nodes"])

        mock_raw.assert_called_once()
        call_kwargs = mock_raw.call_args[1]
        assert call_kwargs["args"] == ["top", "nodes"]
        assert call_kwargs["timeout"] == 30
        assert call_kwargs["context"] == ""
        assert result is mock_result
        assert "NAME  CPU  MEM\n" in target._raw_outputs


# ---------------------------------------------------------------------------
# BaseTarget run_db_command helper
# ---------------------------------------------------------------------------

def test_run_db_command_delegates() -> None:
    """run_db_command executes commands over ssh."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: CommandResult = CommandResult(
        command="ssh 10.0.0.10 nodetool status",
        exit_code=0, stdout="Datacenter: dc1\n", stderr="",
        duration_seconds=0.4, success=True, timed_out=False,
    )

    # mock ssh.to(host).run(command) -> result
    mock_ssh_target: MagicMock = MagicMock()
    mock_ssh_target.run.return_value = mock_result

    with patch.object(target, 'ssh') as mock_ssh:
        mock_ssh.to.return_value = mock_ssh_target

        result: CommandResult = target.run_db_command("10.0.0.10", "nodetool status")

        # no ssh_key in config, so just ssh.to(host).run(command)
        mock_ssh.to.assert_called_once_with("10.0.0.10")
        mock_ssh_target.run.assert_called_once_with("nodetool status")
        assert result is mock_result
        assert "Datacenter: dc1\n" in target._raw_outputs


# ---------------------------------------------------------------------------
# BaseTarget http_get helper
# ---------------------------------------------------------------------------

def test_http_get_success_tracks_body() -> None:
    """http_get saves the response body when things work."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: HttpResult = HttpResult(
        url="http://localhost:8080/health",
        status_code=200,
        body='{"status": "ok"}',
        headers={},
        duration_seconds=0.1,
        success=True,
        error=None,
    )

    with patch("src.lib.base_target.http_get", return_value=mock_result) as mock_http:
        result: HttpResult = target.http_get("http://localhost:8080/health")

        mock_http.assert_called_once_with(url="http://localhost:8080/health", timeout=15)
        assert result is mock_result
        assert '{"status": "ok"}' in target._raw_outputs
        assert "GET http://localhost:8080/health" in target._commands_run


def test_http_get_failure_tracks_error() -> None:
    """http_get records the error when the request fails."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: HttpResult = HttpResult(
        url="http://unreachable:8080",
        status_code=0,
        body="",
        headers={},
        duration_seconds=0.01,
        success=False,
        error="Connection refused",
    )

    with patch("src.lib.base_target.http_get", return_value=mock_result):
        target.http_get("http://unreachable:8080")

        assert "Connection refused" in target._raw_outputs


# ---------------------------------------------------------------------------
# BaseTarget http_get_via_ssh helper
# ---------------------------------------------------------------------------

def test_http_get_via_ssh_delegates() -> None:
    """http_get_via_ssh calls the helper function."""
    target: _SimpleTarget = _SimpleTarget(_make_config(), _make_terminal(), _make_logger())

    mock_result: CommandResult = CommandResult(
        command="ssh 10.0.0.1 curl http://internal/health",
        exit_code=0, stdout='{"ok": true}\n200', stderr="",
        duration_seconds=0.3, success=True, timed_out=False,
    )

    with patch("src.lib.base_target.http_get_via_ssh", return_value=mock_result) as mock_via:
        result: CommandResult = target.http_get_via_ssh("http://internal/health", "10.0.0.1")

        mock_via.assert_called_once_with(
            url="http://internal/health",
            ssh_host="10.0.0.1",
            config=target.config,
        )
        assert result is mock_result
