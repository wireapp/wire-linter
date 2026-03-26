"""Unit tests for the command execution module.

Covers run_command with successful commands, failing commands, timeout handling,
custom environment variables, custom working directory, and stderr capture modes.
"""

from __future__ import annotations

import os
import tempfile

from src.lib.command import run_command, CommandResult


# ---------------------------------------------------------------------------
# run_command successful execution
# ---------------------------------------------------------------------------

def test_run_command_echo() -> None:
    """run_command captures stdout from simple echo command."""
    result: CommandResult = run_command(['echo', 'hello world'])

    assert result.success is True, f"Expected success, got exit_code={result.exit_code}"
    assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}"
    assert 'hello world' in result.stdout, f"Expected 'hello world' in stdout: {result.stdout!r}"
    assert result.timed_out is False, "Should not have timed out"
    assert result.duration_seconds >= 0, "Duration should be non-negative"
    assert result.command == 'echo hello\\ world' or 'echo' in result.command, \
        f"Command string should contain 'echo': {result.command!r}"


def test_run_command_exit_code_zero() -> None:
    """exit_code=0 and success=True for 'true' command."""
    result: CommandResult = run_command(['true'])

    assert result.exit_code == 0
    assert result.success is True
    assert result.timed_out is False


# ---------------------------------------------------------------------------
# run_command failing commands
# ---------------------------------------------------------------------------

def test_run_command_failure() -> None:
    """run_command reports failure for non-zero exit code."""
    result: CommandResult = run_command(['false'])

    assert result.success is False, "Command 'false' should report failure"
    assert result.exit_code != 0, f"Expected non-zero exit code, got {result.exit_code}"
    assert result.timed_out is False, "Should not have timed out"


def test_run_command_nonexistent_command() -> None:
    """run_command returns failed result for nonexistent binary."""
    result: CommandResult = run_command(['__nonexistent_command_xyz_123__'])

    # Reports failure without raising exception
    assert result.success is False, "Nonexistent command should not be successful"
    assert result.exit_code == -1, f"Expected exit_code -1, got {result.exit_code}"
    assert result.timed_out is False, "Should not have timed out"
    assert "not found" in result.stderr.lower(), f"Expected 'not found' in stderr, got: {result.stderr}"


# ---------------------------------------------------------------------------
# run_command timeout
# ---------------------------------------------------------------------------

def test_run_command_timeout() -> None:
    """run_command handles timeouts by killing the process."""
    # Sleep 60s but timeout after 1s
    result: CommandResult = run_command(['sleep', '60'], timeout=1)

    assert result.timed_out is True, "Should have timed out"
    assert result.success is False, "Timed out command should not be successful"
    assert result.exit_code == -1, f"Expected exit_code -1 for timeout, got {result.exit_code}"
    assert result.duration_seconds >= 0.5, "Should have waited at least ~1 second"


# ---------------------------------------------------------------------------
# run_command stderr capture
# ---------------------------------------------------------------------------

def test_run_command_captures_stderr() -> None:
    """stderr captured separately when capture_stderr=True."""
    # bash -c to write to stderr
    result: CommandResult = run_command(
        ['bash', '-c', 'echo error_msg >&2; echo stdout_msg'],
        capture_stderr=True,
    )

    assert 'stdout_msg' in result.stdout, f"Expected 'stdout_msg' in stdout: {result.stdout!r}"
    assert 'error_msg' in result.stderr, f"Expected 'error_msg' in stderr: {result.stderr!r}"


def test_run_command_merged_stderr() -> None:
    """stderr merges into stdout when capture_stderr=False."""
    result: CommandResult = run_command(
        ['bash', '-c', 'echo error_msg >&2; echo stdout_msg'],
        capture_stderr=False,
    )

    # Both messages in stdout when stderr merged
    assert 'stdout_msg' in result.stdout, f"Expected 'stdout_msg' in stdout: {result.stdout!r}"
    assert 'error_msg' in result.stdout, f"Expected 'error_msg' in stdout (merged): {result.stdout!r}"
    # stderr empty when merged
    assert result.stderr == '', f"Expected empty stderr when merged, got: {result.stderr!r}"


# ---------------------------------------------------------------------------
# run_command custom environment
# ---------------------------------------------------------------------------

def test_run_command_custom_env() -> None:
    """Custom environment variables passed to subprocess."""
    result: CommandResult = run_command(
        ['bash', '-c', 'echo $TEST_VAR_XYZ'],
        env={'TEST_VAR_XYZ': 'custom_value_123'},
    )

    assert result.success is True
    assert 'custom_value_123' in result.stdout, \
        f"Expected 'custom_value_123' in stdout: {result.stdout!r}"


def test_run_command_env_merges_with_current() -> None:
    """Custom env merged with current, not replaced."""
    # PATH still available since env merged
    result: CommandResult = run_command(
        ['bash', '-c', 'echo $PATH'],
        env={'TEST_EXTRA': 'value'},
    )

    assert result.success is True
    # PATH not empty (inherited from env)
    assert len(result.stdout.strip()) > 0, "PATH should be inherited from current env"


# ---------------------------------------------------------------------------
# run_command custom working directory
# ---------------------------------------------------------------------------

def test_run_command_custom_cwd() -> None:
    """Custom working directory used for subprocess."""
    # Create temp directory to use as cwd
    with tempfile.TemporaryDirectory() as tmpdir:
        result: CommandResult = run_command(['pwd'], cwd=tmpdir)

        assert result.success is True
        # Output is realpath of temp directory
        expected: str = os.path.realpath(tmpdir)
        actual: str = os.path.realpath(result.stdout.strip())
        assert actual == expected, \
            f"Expected cwd {expected!r}, got {actual!r}"


# ---------------------------------------------------------------------------
# run_command CommandResult structure
# ---------------------------------------------------------------------------

def test_command_result_fields() -> None:
    """All CommandResult fields populated correctly."""
    result: CommandResult = run_command(['echo', 'test'])

    # All fields present with correct types
    assert isinstance(result.command, str), "command should be str"
    assert isinstance(result.exit_code, int), "exit_code should be int"
    assert isinstance(result.stdout, str), "stdout should be str"
    assert isinstance(result.stderr, str), "stderr should be str"
    assert isinstance(result.duration_seconds, float), "duration_seconds should be float"
    assert isinstance(result.success, bool), "success should be bool"
    assert isinstance(result.timed_out, bool), "timed_out should be bool"


def test_run_command_multiline_output() -> None:
    """Multiline stdout captured completely."""
    result: CommandResult = run_command(
        ['bash', '-c', 'echo line1; echo line2; echo line3'],
    )

    assert result.success is True
    lines: list[str] = result.stdout.strip().split('\n')
    assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}: {lines}"
    assert lines[0] == 'line1'
    assert lines[1] == 'line2'
    assert lines[2] == 'line3'
