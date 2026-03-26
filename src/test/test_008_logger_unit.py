"""Unit tests for the logger module.

Covers log level filtering, message formatting, output to stderr,
and all convenience methods (debug, info, warning, error).
"""

from __future__ import annotations

import io
import sys

from src.lib.logger import Logger, LogLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_logger_output(
    level: LogLevel,
    action: object = None,
) -> str:
    """Run an action on a Logger and capture its stderr output."""
    logger: Logger = Logger(level=level)
    captured: io.StringIO = io.StringIO()

    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        if action:
            action(logger)  # type: ignore[operator]
    finally:
        sys.stderr = old_stderr

    return captured.getvalue()


# ---------------------------------------------------------------------------
# LogLevel value ordering
# ---------------------------------------------------------------------------

def test_log_level_ordering() -> None:
    """Verify log levels have correct integer ordering for filtering."""
    assert LogLevel.DEBUG.value < LogLevel.INFO.value
    assert LogLevel.INFO.value < LogLevel.WARNING.value
    assert LogLevel.WARNING.value < LogLevel.ERROR.value


# ---------------------------------------------------------------------------
# Logger level filtering
# ---------------------------------------------------------------------------

def test_logger_debug_level_shows_all() -> None:
    """DEBUG level should show all messages including debug."""
    output: str = _capture_logger_output(
        level=LogLevel.DEBUG,
        action=lambda log: (
            log.debug('dbg'),
            log.info('inf'),
            log.warning('wrn'),
            log.error('err'),
        ),
    )

    assert 'dbg' in output
    assert 'inf' in output
    assert 'wrn' in output
    assert 'err' in output


def test_logger_info_level_filters_debug() -> None:
    """INFO level should suppress debug messages."""
    output: str = _capture_logger_output(
        level=LogLevel.INFO,
        action=lambda log: (
            log.debug('hidden'),
            log.info('visible'),
        ),
    )

    assert 'hidden' not in output, f"Debug should be filtered: {output!r}"
    assert 'visible' in output


def test_logger_warning_level_filters_info() -> None:
    """WARNING level should suppress debug and info messages."""
    output: str = _capture_logger_output(
        level=LogLevel.WARNING,
        action=lambda log: (
            log.debug('hidden_d'),
            log.info('hidden_i'),
            log.warning('visible_w'),
            log.error('visible_e'),
        ),
    )

    assert 'hidden_d' not in output
    assert 'hidden_i' not in output
    assert 'visible_w' in output
    assert 'visible_e' in output


def test_logger_error_level_filters_all_below() -> None:
    """ERROR level should only show error messages."""
    output: str = _capture_logger_output(
        level=LogLevel.ERROR,
        action=lambda log: (
            log.debug('hidden_d'),
            log.info('hidden_i'),
            log.warning('hidden_w'),
            log.error('visible_e'),
        ),
    )

    assert 'hidden_d' not in output
    assert 'hidden_i' not in output
    assert 'hidden_w' not in output
    assert 'visible_e' in output


# ---------------------------------------------------------------------------
# Logger message format
# ---------------------------------------------------------------------------

def test_logger_message_format_contains_level() -> None:
    """log output should contain the level name."""
    output: str = _capture_logger_output(
        level=LogLevel.INFO,
        action=lambda log: log.info('test message'),
    )

    assert '[INFO]' in output, f"Should contain [INFO]: {output!r}"


def test_logger_message_format_contains_timestamp() -> None:
    """log output should contain a timestamp in YYYY-MM-DD HH:MM:SS format."""
    output: str = _capture_logger_output(
        level=LogLevel.INFO,
        action=lambda log: log.info('timestamp test'),
    )

    # check for YYYY-MM-DD HH:MM:SS pattern
    import re
    assert re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', output), \
        f"Should contain timestamp: {output!r}"


def test_logger_message_format_contains_dash() -> None:
    """log output should use em-dash separator between timestamp and message."""
    output: str = _capture_logger_output(
        level=LogLevel.INFO,
        action=lambda log: log.info('dash test'),
    )

    # uses U+2014 EM DASH
    assert '\u2014' in output, f"Should contain em-dash: {output!r}"


def test_logger_message_format_contains_message() -> None:
    """the actual message text should appear in output."""
    output: str = _capture_logger_output(
        level=LogLevel.INFO,
        action=lambda log: log.info('the actual message'),
    )

    assert 'the actual message' in output


# ---------------------------------------------------------------------------
# Logger output goes to stderr
# ---------------------------------------------------------------------------

def test_logger_writes_to_stderr_not_stdout() -> None:
    """log output should go to stderr, not stdout."""
    logger: Logger = Logger(level=LogLevel.INFO)

    # capture both streams
    captured_stdout: io.StringIO = io.StringIO()
    captured_stderr: io.StringIO = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = captured_stdout
    sys.stderr = captured_stderr
    try:
        logger.info('stderr only')
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    assert captured_stdout.getvalue() == '', \
        f"Logger should NOT write to stdout: {captured_stdout.getvalue()!r}"
    assert 'stderr only' in captured_stderr.getvalue(), \
        f"Logger should write to stderr: {captured_stderr.getvalue()!r}"


# ---------------------------------------------------------------------------
# Logger convenience methods
# ---------------------------------------------------------------------------

def test_logger_debug_method() -> None:
    """debug() should log with DEBUG level name."""
    output: str = _capture_logger_output(
        level=LogLevel.DEBUG,
        action=lambda log: log.debug('debug message'),
    )

    assert '[DEBUG]' in output
    assert 'debug message' in output


def test_logger_warning_method() -> None:
    """warning() should log with WARNING level name."""
    output: str = _capture_logger_output(
        level=LogLevel.WARNING,
        action=lambda log: log.warning('warning message'),
    )

    assert '[WARNING]' in output
    assert 'warning message' in output


def test_logger_error_method() -> None:
    """error() should log with ERROR level name."""
    output: str = _capture_logger_output(
        level=LogLevel.ERROR,
        action=lambda log: log.error('error message'),
    )

    assert '[ERROR]' in output
    assert 'error message' in output
