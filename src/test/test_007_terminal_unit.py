"""Unit tests for the terminal output module.

Covers Terminal output methods across verbosity levels, color toggling,
summary formatting, and edge cases. Uses io.StringIO to capture stdout.
"""

from __future__ import annotations

# External
import io
import sys
from unittest.mock import MagicMock
from typing import Any

# Ours
from src.lib.terminal import (
    Terminal,
    Verbosity,
    ICON_TARGET,
    ICON_SUCCESS,
    ICON_FAILED,
    ICON_IN_PROGRESS,
    ICON_COMMAND,
    ICON_WARNING,
    ICON_INFO,
    ICON_ARROW,
    COLOR_GREEN,
    COLOR_RED,
    STYLE_RESET,
    STYLE_BOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_terminal_output(
    verbosity: Verbosity = Verbosity.NORMAL,
    use_color: bool = False,
    action: Any = None,
) -> str:
    """Run an action on a Terminal and capture its stdout."""
    terminal: Terminal = Terminal(verbosity=verbosity, use_color=use_color)
    captured: io.StringIO = io.StringIO()

    # save the real stdout for restoration
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        if action:
            action(terminal)
    finally:
        # restore stdout
        sys.stdout = old_stdout

    return captured.getvalue()


# ---------------------------------------------------------------------------
# Terminal target_start
# ---------------------------------------------------------------------------

def test_target_start_normal() -> None:
    """target_start should print target icon and path in normal mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.target_start('databases/cassandra/status'),
    )

    assert ICON_TARGET in output, f"Should contain target icon: {output!r}"
    assert 'databases/cassandra/status' in output, f"Should contain path: {output!r}"


def test_target_start_quiet() -> None:
    """target_start should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.target_start('databases/cassandra/status'),
    )

    # quiet mode should produce no output
    assert output == '', f"Should be empty in QUIET mode, got {output!r}"


# ---------------------------------------------------------------------------
# Terminal target_success
# ---------------------------------------------------------------------------

def test_target_success_normal() -> None:
    """target_success should print the result."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.target_success('test/path', 'UN', 'status'),
    )

    # path is shown by target_start
    assert ICON_SUCCESS in output
    assert 'UN' in output
    assert 'status' in output


def test_target_success_quiet() -> None:
    """target_success should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.target_success('test/path', 'UN', 'status'),
    )

    assert output == ''


def test_target_success_empty_unit() -> None:
    """target_success should handle empty unit string."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.target_success('test/path', 42, ''),
    )

    # value should still render without a unit
    assert '42' in output


# ---------------------------------------------------------------------------
# Terminal target_failure
# ---------------------------------------------------------------------------

def test_target_failure_normal() -> None:
    """target_failure should print the error message."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.target_failure('test/path', 'Connection refused'),
    )

    # path is shown by target_start
    assert ICON_FAILED in output
    assert 'Connection refused' in output


def test_target_failure_quiet() -> None:
    """target_failure should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.target_failure('test/path', 'error'),
    )

    assert output == ''


# ---------------------------------------------------------------------------
# Terminal step
# ---------------------------------------------------------------------------

def test_step_normal() -> None:
    """step should print indented message with in-progress icon."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.step('Checking status...'),
    )

    assert ICON_IN_PROGRESS in output
    assert 'Checking status...' in output

    # visually indented under the target header
    assert output.startswith('  '), f"Should be indented: {output!r}"


def test_step_quiet() -> None:
    """step should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.step('Checking status...'),
    )

    assert output == ''


# ---------------------------------------------------------------------------
# Terminal command
# ---------------------------------------------------------------------------

def test_command_verbose_only() -> None:
    """command output should only show in verbose mode."""
    # in normal mode it should remain hidden to avoid noise
    output_normal: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.command('ssh node1 uptime'),
    )
    assert output_normal == '', f"Command should not show in NORMAL: {output_normal!r}"

    # verbose mode should show it for debugging
    output_verbose: str = _capture_terminal_output(
        verbosity=Verbosity.VERBOSE,
        action=lambda t: t.command('ssh node1 uptime'),
    )
    assert ICON_COMMAND in output_verbose
    assert 'ssh node1 uptime' in output_verbose


# ---------------------------------------------------------------------------
# Terminal command_output
# ---------------------------------------------------------------------------

def test_command_output_verbose_only() -> None:
    """command output should only show in verbose mode."""
    # raw output shouldn't appear in normal mode, it would flood the screen
    output_normal: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.command_output('line1\nline2'),
    )
    assert output_normal == ''

    # verbose mode should show all lines for inspection
    output_verbose: str = _capture_terminal_output(
        verbosity=Verbosity.VERBOSE,
        action=lambda t: t.command_output('line1\nline2'),
    )
    assert 'line1' in output_verbose
    assert 'line2' in output_verbose


def test_command_output_truncation() -> None:
    """command output should be truncated after max_lines."""
    # 15 lines exceeds max_lines=5, remainder is summarized
    long_output: str = '\n'.join(f'line{i}' for i in range(15))

    output: str = _capture_terminal_output(
        verbosity=Verbosity.VERBOSE,
        action=lambda t: t.command_output(long_output, max_lines=5),
    )

    # with max_lines=5, shows first half (2) + last half (2)
    assert 'line0' in output
    assert 'line1' in output

    # truncation notice should indicate lines omitted
    assert '10 more lines' in output


def test_command_output_empty() -> None:
    """empty command output should produce no output."""
    # completely empty string produces nothing
    output: str = _capture_terminal_output(
        verbosity=Verbosity.VERBOSE,
        action=lambda t: t.command_output(''),
    )
    assert output == ''

    # whitespace-only output also produces nothing
    output_whitespace: str = _capture_terminal_output(
        verbosity=Verbosity.VERBOSE,
        action=lambda t: t.command_output('   \n  \n'),
    )
    assert output_whitespace == ''


# ---------------------------------------------------------------------------
# Terminal info, warning, error
# ---------------------------------------------------------------------------

def test_info_normal() -> None:
    """info should print in normal mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.info('Loading config...'),
    )

    assert ICON_INFO in output
    assert 'Loading config...' in output


def test_info_quiet() -> None:
    """info should be suppressed in quiet mode."""
    # info messages are informational only, quiet keeps output minimal
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.info('Loading config...'),
    )
    assert output == ''


def test_warning_normal() -> None:
    """warning should print in normal mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.warning('Slow response'),
    )

    assert ICON_WARNING in output
    assert 'Slow response' in output


def test_warning_quiet() -> None:
    """warning should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.warning('Slow response'),
    )
    assert output == ''


def test_error_always_prints() -> None:
    """error should print even in quiet mode."""
    output_quiet: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.error('Fatal error occurred'),
    )

    # errors should bypass verbosity filtering
    assert ICON_FAILED in output_quiet
    assert 'Fatal error occurred' in output_quiet


# ---------------------------------------------------------------------------
# Terminal blank_line and header
# ---------------------------------------------------------------------------

def test_blank_line_normal() -> None:
    """blank_line should print an empty line in normal mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.blank_line(),
    )

    # exactly one newline
    assert output == '\n', f"Expected single newline, got {output!r}"


def test_blank_line_quiet() -> None:
    """blank_line should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.blank_line(),
    )
    assert output == ''


def test_header_normal() -> None:
    """header should print decorated title."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.header('Wire Fact Gathering Tool'),
    )

    assert 'Wire Fact Gathering Tool' in output

    # box-drawing decoration should visually separate the header
    assert '═══' in output


def test_header_quiet() -> None:
    """header should be suppressed in quiet mode."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.header('Wire Fact Gathering Tool'),
    )
    assert output == ''


# ---------------------------------------------------------------------------
# Terminal color control
# ---------------------------------------------------------------------------

def test_color_enabled() -> None:
    """ANSI codes should be present when color is enabled."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        use_color=True,
        action=lambda t: t.error('color test'),
    )

    # error uses COLOR_RED with ANSI escape sequence
    assert '\033[' in output, f"Should contain ANSI escape codes: {output!r}"


def test_color_disabled() -> None:
    """no ANSI codes should appear when color is disabled."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        use_color=False,
        action=lambda t: t.error('no color test'),
    )

    # no escape codes when color is off
    assert '\033[' not in output, f"Should NOT contain ANSI escape codes: {output!r}"
    assert 'no color test' in output


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------

def test_summary_all_passed() -> None:
    """summary output should show all targets passed."""
    # build mock TargetResults with success=True
    mock_results: list[MagicMock] = []
    for i in range(3):
        r: MagicMock = MagicMock()
        r.success = True
        r.duration_seconds = 1.0
        r.data_point = MagicMock()
        r.data_point.path = f'test/target/{i}'
        mock_results.append(r)

    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.summary(mock_results, runtime_seconds=3.0),
    )

    assert 'Summary' in output
    assert 'Total: 3 targets' in output
    assert 'Collected: 3' in output
    assert 'Failed: 0' in output

    # runtime should appear for performance monitoring
    assert '3s' in output


def test_summary_with_failures() -> None:
    """summary output should include failure details."""
    # mix of passed and failed results
    passed: MagicMock = MagicMock()
    passed.success = True
    passed.duration_seconds = 1.0
    passed.data_point = MagicMock()
    passed.data_point.path = 'test/ok'

    failed: MagicMock = MagicMock()
    failed.success = False
    failed.duration_seconds = 2.0
    failed.data_point = MagicMock()
    failed.data_point.path = 'test/fail'
    failed.error = 'Connection refused'

    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.summary([passed, failed], runtime_seconds=3.0),
    )

    assert 'Total: 2 targets' in output
    assert 'Collected: 1' in output
    assert 'Failed: 1' in output

    # failure list should identify which target failed and why
    assert 'Collection failures:' in output
    assert 'test/fail' in output
    assert 'Connection refused' in output


def test_summary_auto_runtime() -> None:
    """summary should calculate runtime from results when not provided."""
    # two results taking 30s each should sum to 60s
    results: list[MagicMock] = []
    for _ in range(2):
        r: MagicMock = MagicMock()
        r.success = True
        r.duration_seconds = 30.0
        r.data_point = MagicMock()
        r.data_point.path = 'test/auto'
        results.append(r)

    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.summary(results),
    )

    # 60 seconds should display as minutes+seconds
    assert '1m' in output


def test_summary_always_prints_in_quiet() -> None:
    """summary should print even in quiet mode."""
    r: MagicMock = MagicMock()
    r.success = True
    r.duration_seconds = 5.0
    r.data_point = MagicMock()
    r.data_point.path = 'test/quiet'

    output: str = _capture_terminal_output(
        verbosity=Verbosity.QUIET,
        action=lambda t: t.summary([r], runtime_seconds=5.0),
    )

    # summary should always show, even in quiet
    assert 'Summary' in output, "Summary should print even in QUIET mode"
    assert 'Total: 1 targets' in output


def test_summary_empty_results() -> None:
    """summary should handle empty results list."""
    output: str = _capture_terminal_output(
        verbosity=Verbosity.NORMAL,
        action=lambda t: t.summary([], runtime_seconds=0.0),
    )

    # should show zero totals
    assert 'Total: 0 targets' in output
    assert 'Collected: 0' in output
    assert 'Failed: 0' in output
