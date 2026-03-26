"""Terminal output with tree-like formatting, UTF-8 icons, ANSI colors,
and multiple verbosity levels.

Handles all the visual output for runner progress. Everything goes through
Terminal so we get consistent formatting and respect verbosity settings.

Indentation hierarchy:
    🎯 target/path                         ← Level 0: target header
      ○ Step description...                ← Level 1: steps and results
        →  1 | first output line...        ← Level 2: numbered output (up to 10 lines)
           2 | second output line...
        ❯ full command (verbose only)      ← Level 2: command string
           1 | raw output... (verbose)     ← Level 3: numbered raw output
"""

from __future__ import annotations

import re
import shutil
import sys
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.lib.base_target import TargetResult


class Verbosity(Enum):
    """Output verbosity levels."""

    # Summary only suppresses all progress output
    QUIET = "quiet"

    # Tree output with key info default level
    NORMAL = "normal"

    # Full command output including stdout/stderr
    VERBOSE = "verbose"


# UTF-8 icon constants for terminal output
ICON_TARGET = "🎯"        # U+1F3AF
ICON_IN_PROGRESS = "○"    # U+25CB
ICON_COMPLETED = "●"      # U+25CF
ICON_FAILED = "✗"         # U+2717
ICON_COMMAND = "❯"        # U+276F
ICON_SUCCESS = "✓"        # U+2713
ICON_WARNING = "⚠"        # U+26A0
ICON_INFO = "ℹ"           # U+2139
ICON_ARROW = "→"          # U+2192

# Matches all ANSI CSI escape sequences (colors, cursor movement, erase, etc.)
ANSI_ESCAPE: re.Pattern[str] = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# ANSI color/style escape codes
COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_CYAN = "\033[36m"
COLOR_GRAY = "\033[90m"
STYLE_BOLD = "\033[1m"
STYLE_RESET = "\033[0m"


def _get_terminal_width() -> int:
    """Current terminal width, defaulting to 120 if not a TTY."""
    return shutil.get_terminal_size((120, 24)).columns


def _truncate_lines(
    lines: list[str],
    max_lines: int = 10,
) -> list[tuple[int | None, str]]:
    """Truncate lines to max_lines, keeping original line numbers.

    If there are fewer lines than max_lines, returns them all with their
    original 1-based numbers. Otherwise returns the first half and last
    half with a [...] marker (line_number=None) in between.
    """
    total: int = len(lines)

    if total <= max_lines:
        return [(i + 1, line) for i, line in enumerate(lines)]

    # Split evenly: first half and last half
    half: int = max_lines // 2
    omitted: int = total - (half * 2)

    result: list[tuple[int | None, str]] = []

    # First half original line numbers 1..half
    for i in range(half):
        result.append((i + 1, lines[i]))

    # Omission marker
    result.append((None, f"[... {omitted} more lines ...]"))

    # Last half original line numbers (total-half+1)..total
    for i in range(total - half, total):
        result.append((i + 1, lines[i]))

    return result


class Terminal:
    """Handles tree-formatted terminal output with colors and indentation."""

    def __init__(
        self,
        verbosity: Verbosity = Verbosity.NORMAL,
        use_color: bool = True,
    ) -> None:
        """Set up verbosity and color preferences."""
        self._verbosity: Verbosity = verbosity
        self._use_color: bool = use_color

    def _color(self, text: str, color: str) -> str:
        """Wrap text in ANSI color codes if colors are enabled.

        Central point for all color output every method that needs
        color calls this instead of building escape sequences directly.
        """
        if self._use_color:
            return f"{color}{text}{STYLE_RESET}"
        return text

    def _print(self, message: str) -> None:
        """Print message to stdout and flush immediately for real-time output."""
        print(message, file=sys.stdout, flush=True)

    def target_start(self, path: str) -> None:
        """Print the target header line when execution starts.

        Format: 🎯 databases/cassandra/cluster_status
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(f"{ICON_TARGET} {self._color(path, COLOR_BLUE)}")

    def target_success(self, path: str, value: Any, unit: str | None) -> None:
        """Print target success result (indented under the target header).

        Green checkmark means data was collected successfully. The value
        is just the collected data health interpretation happens elsewhere.

        Format: ✓ UN
        """
        if self._verbosity is Verbosity.QUIET:
            return

        # Format value with unit when present, omit when None
        value_str: str = f"{value} {unit}" if unit else str(value)
        self._print(
            f"  {self._color(ICON_SUCCESS, COLOR_GREEN)}"
            f" {value_str}"
        )

    def target_not_applicable(self, path: str, reason: str = "") -> None:
        """Print a 'not applicable' line when a target is skipped.

        Happens when the target requires external access, when a service
        isn't deployed, or when a runtime check determines data can't be
        gathered. Gray dash means intentionally skipped, not failed.

        Args:
            path: Target path (for future use in structured output).
            reason: Why the target was skipped. Falls back to a generic
                message when empty.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        if not reason:
            reason = "requires external access; re-run from outside"
        self._print(
            f"  {self._color(f'– skipped ({reason})', COLOR_GRAY)}"
        )

    def target_failure(self, path: str, error: str) -> None:
        """Print target failure result (indented under the target header).

        Red cross means data collection failed, not that the system is
        unhealthy. The error says why collection failed.

        Format: ✗ Connection refused
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(
            f"  {self._color(ICON_FAILED + ' ' + error, COLOR_RED)}"
        )

    def command_result(self, output: str) -> None:
        """Print numbered command output lines (up to 10, truncated with [...]).

        Shows at level 2 under steps so the operator can see data without
        needing verbose mode. If output exceeds 10 lines, shows first 5 and
        last 5 with a [...] marker. Lines wider than the terminal get cropped.

        Format: → 1 | first line of output
                  2 | second line of output
        """
        if self._verbosity is Verbosity.QUIET:
            return

        stripped: str = output.strip()
        if not stripped:
            return

        # Skip blank lines for cleaner output
        lines: list[str] = [line for line in stripped.splitlines() if line.strip()]

        if not lines:
            return

        # Pretty-print single-line JSON so it's readable with line numbers
        if lines[0].startswith("{") and len(lines) == 1:
            import json
            try:
                parsed: object = json.loads(lines[0])
                formatted: str = json.dumps(parsed, indent=2)
                lines = [line for line in formatted.splitlines() if line.strip()]
            except (json.JSONDecodeError, ValueError):
                pass

        total_lines: int = len(lines)
        numbered: list[tuple[int | None, str]] = _truncate_lines(lines, max_lines=10)

        # Pad line numbers to match the largest original line number width
        num_width: int = len(str(total_lines))

        # Calculate available content width after prefix:
        # 4 (indent) + 2 ("→ " or "  ") + num_width + 3 (" | ") = 9 + num_width
        term_width: int = _get_terminal_width()
        content_width: int = term_width - 9 - num_width

        for index, (line_num, content) in enumerate(numbered):
            if line_num is None:
                # [...] marker align with content column
                padding: str = " " * (num_width + 3)
                text: str = f"{padding}{content}"
            else:
                num_str: str = str(line_num).rjust(num_width)

                # Expand tabs so len() reflects visual column count
                content = content.expandtabs()

                # Crop lines that would overflow the terminal
                if content_width > 3 and len(content) > content_width:
                    content = content[: content_width - 3] + "..."

                text = f"{num_str} | {content}"

            # First line gets arrow prefix; continuation lines align with spaces
            if index == 0:
                self._print(f"    {self._color(ICON_ARROW + ' ' + text, COLOR_GRAY)}")
            else:
                self._print(f"      {self._color(text, COLOR_GRAY)}")

    def target_explanation(self, message: str) -> None:
        """Print explanation of the target under the target header.

        Why this check exists and what healthy/unhealthy means. Shown in
        gray to visually separate it from the target path.

        Format: message text here
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(f"  {self._color(message, COLOR_GRAY)}")

    def health_info(self, message: str) -> None:
        """Print secondary health assessment line (informational only).

        Not a pass/fail indicator, just context about what the collected
        data means. Shown in gray to visually separate it from the primary
        success/failure result.

        Format: ℹ All nodes Up/Normal
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(f"  {self._color(ICON_INFO + ' ' + message, COLOR_GRAY)}")

    def step(self, message: str) -> None:
        """Print a step within a target (indented one level).

        Format: ○ Checking Cassandra cluster status...
        Shown in NORMAL and VERBOSE modes, not in QUIET.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        # 2-space indent creates the visual tree under the target header
        self._print(f"  {ICON_IN_PROGRESS} {message}")

    def command(self, cmd: str) -> None:
        """Print a command being executed (indented two levels).

        Format: ❯ ssh datanode1 nodetool status
        Only shown in VERBOSE mode.
        """
        if self._verbosity is not Verbosity.VERBOSE:
            return
        # 4-space indent nests commands under steps visually
        self._print(f"    {self._color(ICON_COMMAND + ' ' + cmd, COLOR_CYAN)}")

    def command_stderr(self, stderr: str) -> None:
        """Print stderr content in yellow at the command-output level.

        Shown whenever stderr is non-empty, regardless of verbosity (except
        QUIET). Helps diagnose failures where stdout was empty, like cqlsh
        authentication errors that would otherwise be invisible.

        Format: ⚠ Connection refused: connect to localhost:9042
        """
        if self._verbosity is Verbosity.QUIET:
            return

        stripped: str = stderr.strip()
        if not stripped:
            return

        # Show up to 5 lines of stderr to surface errors without flooding
        lines: list[str] = stripped.splitlines()
        for line in lines[:5]:
            self._print(
                f"    {self._color(ICON_WARNING + ' ' + line, COLOR_YELLOW)}"
            )

        # If stderr has more lines, indicate how many got cut
        if len(lines) > 5:
            omitted: int = len(lines) - 5
            self._print(
                f"    {self._color(f'  ... ({omitted} more lines)', COLOR_YELLOW)}"
            )

    def command_output(self, output: str, max_lines: int = 10) -> None:
        """Print numbered command output (indented three levels, truncated).

        Shows up to max_lines in dim gray, only in VERBOSE mode. If output
        exceeds max_lines, shows first half and last half with a [...]
        marker. Lines wider than the terminal get cropped.
        """
        if self._verbosity is not Verbosity.VERBOSE:
            return

        # Skip empty output
        if not output or not output.strip():
            return

        lines: list[str] = output.strip().splitlines()
        total_lines: int = len(lines)
        numbered: list[tuple[int | None, str]] = _truncate_lines(lines, max_lines=max_lines)

        # Pad line numbers to match the largest original line number width
        num_width: int = len(str(total_lines))

        # Calculate available content width after prefix:
        # 6 (indent) + num_width + 3 (" | ") = 9 + num_width
        term_width: int = _get_terminal_width()
        content_width: int = term_width - 9 - num_width

        for line_num, content in numbered:
            if line_num is None:
                # [...] marker align with content column
                padding: str = " " * (num_width + 3)
                self._print(f"      {self._color(f'{padding}{content}', COLOR_GRAY)}")
            else:
                num_str: str = str(line_num).rjust(num_width)

                # Expand tabs so len() reflects visual column count
                content = content.expandtabs()

                # Crop lines that would overflow the terminal
                if content_width > 3 and len(content) > content_width:
                    content = content[: content_width - 3] + "..."

                self._print(f"      {self._color(f'{num_str} | {content}', COLOR_GRAY)}")

    def info(self, message: str) -> None:
        """Print an info message at top level.

        Format: ℹ message
        Suppressed in QUIET mode.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(f"{ICON_INFO} {message}")

    def warning(self, message: str) -> None:
        """Print a warning message at top level.

        Format: ⚠ message (in yellow)
        Suppressed in QUIET mode.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(self._color(f"{ICON_WARNING} {message}", COLOR_YELLOW))

    def error(self, message: str) -> None:
        """Print an error message at top level.

        Format: ✗ message (in red)
        Always printed regardless of verbosity errors are never silenced.
        """
        # Errors bypass verbosity check always visible
        self._print(self._color(f"{ICON_FAILED} {message}", COLOR_RED))

    def check_pass(self, label: str) -> None:
        """Print a passing check line with a green checkmark.

        Used by pre-flight checks and other verify-style output.
        Suppressed in QUIET mode.

        Format: ✓ label text here
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(f"  {self._color(ICON_SUCCESS + ' ' + label, COLOR_GREEN)}")

    def check_fail(self, label: str) -> None:
        """Print a failing check line with a red cross.

        Always printed regardless of verbosity failures are never silenced.

        Format: ✗ label text here
        """
        # Failures bypass verbosity always visible
        self._print(f"  {self._color(ICON_FAILED + ' ' + label, COLOR_RED)}")

    def check_skip(self, label: str) -> None:
        """Print a skipped check line with a gray dash.

        Check wasn't attempted because a dependency failed. Suppressed in QUIET mode.

        Format: – label text here
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(f"  {self._color('– ' + label, COLOR_GRAY)}")

    def blank_line(self) -> None:
        """Print a blank line for visual separation.

        Suppressed in QUIET mode.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print("")

    def header(self, title: str) -> None:
        """Print a section header with decoration.

        Format: ═══ Wire Fact Gathering Tool ═══
        Uses U+2550 BOX DRAWINGS DOUBLE HORIZONTAL. Suppressed in QUIET mode.
        """
        if self._verbosity is Verbosity.QUIET:
            return
        self._print(self._color(f"═══ {title} ═══", STYLE_BOLD))

    def summary(
        self,
        results: list[TargetResult],
        runtime_seconds: float | None = None,
    ) -> None:
        """Print the end-of-run summary.

        Always printed regardless of verbosity, even in QUIET mode. Shows
        total targets, collected/failed counts, failures, and runtime.

        «Passed» means data was collected. «Failed» means collection failed,
        not that the system is unhealthy.
        """
        # Summary header bypass QUIET check by printing directly
        self._print(self._color("═══ Summary ═══", STYLE_BOLD))
        self._print("")

        # Count results
        collected: int = sum(1 for r in results if r.success)
        failed: int = sum(1 for r in results if not r.success)
        total: int = len(results)

        # Print counts
        self._print(f"  Total: {total} targets")
        self._print(f"  {self._color(ICON_SUCCESS + ' Collected: ' + str(collected), COLOR_GREEN)}")
        self._print(f"  {self._color(ICON_FAILED + ' Failed: ' + str(failed), COLOR_RED)}")

        # Failure details section these are collection failures, not health issues
        failed_results: list[TargetResult] = [r for r in results if not r.success]
        if failed_results:
            self._print("")
            self._print("  Collection failures:")
            for r in failed_results:
                # Use data_point.path if available, otherwise "unknown"
                path: str = r.data_point.path if r.data_point is not None else "unknown"
                error_msg: str = r.error or "Unknown error"
                self._print(
                    f"    {self._color(ICON_FAILED + ' ' + path + ' - ' + error_msg, COLOR_RED)}"
                )

        # Runtime
        self._print("")
        if runtime_seconds is not None:
            total_secs: float = runtime_seconds
        else:
            total_secs = sum(r.duration_seconds for r in results)

        minutes: int = int(total_secs) // 60
        seconds: int = int(total_secs) % 60

        # Format: "Xm Ys" or just "Ys" if under 60 seconds
        if minutes > 0:
            formatted_time: str = f"{minutes}m {seconds}s"
        else:
            formatted_time = f"{seconds}s"

        self._print(f"  Total runtime: {formatted_time}")


class BufferedTerminal(Terminal):
    """Terminal that captures output into a buffer instead of printing.

    Used in parallel execution mode so each target's output is collected
    independently and flushed atomically when done. Prevents interleaved
    output from concurrent targets each appears as a contiguous block.
    """

    def __init__(
        self,
        verbosity: Verbosity = Verbosity.NORMAL,
        use_color: bool = True,
    ) -> None:
        """Initialize with an empty output buffer."""
        super().__init__(verbosity=verbosity, use_color=use_color)

        # Accumulated output lines each entry is one formatted line
        self._buffer: list[str] = []

    def _print(self, message: str) -> None:
        """Capture the message into the buffer instead of printing.

        Overrides Terminal._print() so all output methods automatically
        buffer their output instead of printing directly.
        """
        self._buffer.append(message)

    def flush_to(self, target_terminal: Terminal) -> None:
        """Flush all buffered output through the given terminal's _print.

        Prints every buffered line in order through the target terminal,
        then clears the buffer. Makes the entire target's output appear
        as one atomic block on the real terminal.
        """
        for message in self._buffer:
            target_terminal._print(message)
        self._buffer.clear()
