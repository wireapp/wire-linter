"""Simple logger for the wire linter runner.

Writes to stderr (never mixes with JSONL output on stdout). Four levels:
DEBUG, INFO, WARNING, ERROR. European UTC timestamps on every line. Flushes
immediately so output appears in real time.

Logger is the main class. Instantiate once per process and pass it around.
"""

from __future__ import annotations

import sys
import datetime
from enum import Enum


class LogLevel(Enum):
    """Log levels."""

    # integers so we can do >= comparisons for filtering
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3


class Logger:
    """Writes log lines to stderr.

    Format: [LEVEL] YYYY-MM-DD HH:mm:ss message
    """

    def __init__(self, level: LogLevel = LogLevel.INFO) -> None:
        """Set up the logger.

        Args:
            level: Minimum level to log. Anything below this is silently dropped.
        """
        self._level: LogLevel = level

    def _log(self, level: LogLevel, message: str) -> None:
        """Write to stderr if the level passes the filter.

        Args:
            level:   Severity level of this message.
            message: The text to log.
        """
        # drop it if below our configured level
        if level.value < self._level.value:
            return

        # utc timestamp
        timestamp: str = datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        # flush immediately so lines show up right away
        print(f"[{level.name}] {timestamp} - {message}", file=sys.stderr, flush=True)

    def debug(self, message: str) -> None:
        """Debug-level message (suppressed in production, useful during dev).

        Args:
            message: Text to log.
        """
        self._log(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        """Info-level message (normal operational stuff).

        Args:
            message: Text to log.
        """
        self._log(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        """Warning-level message (something unexpected but non-fatal).

        Args:
            message: Text to log.
        """
        self._log(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        """Error-level message (something failed and needs attention).

        Args:
            message: Text to log.
        """
        self._log(LogLevel.ERROR, message)
