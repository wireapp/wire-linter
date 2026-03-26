"""Tests for terminal output formatting colors, verbosity levels, etc."""

import io
import unittest
from unittest.mock import patch

from src.lib.terminal import Terminal, Verbosity
from src.lib.output import DataPoint
from src.lib.base_target import TargetResult


class TestTerminal(unittest.TestCase):
    """Test Terminal output colors, verbosity, summary formatting."""

    def _capture_output(
        self,
        verbosity: Verbosity,
        use_color: bool,
        method_name: str,
        *args: object,
    ) -> str:
        """Helper to run a Terminal method and capture its output."""
        terminal = Terminal(verbosity=verbosity, use_color=use_color)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            method = getattr(terminal, method_name)
            method(*args)
            return mock_stdout.getvalue()

    def test_color_output_formatting(self) -> None:
        """Color on means output has ANSI codes."""
        output = self._capture_output(
            Verbosity.NORMAL, True, "target_success", "host/disk_usage", 55, "%"
        )

        # Check for ANSI codes (start and reset)
        self.assertIn("\033[", output)
        self.assertIn("\033[0m", output)

        # And the actual content too
        self.assertIn("host/disk_usage", output)
        self.assertIn("55", output)

    def test_no_color_mode(self) -> None:
        """Color off means no ANSI codes anywhere."""
        terminal = Terminal(verbosity=Verbosity.NORMAL, use_color=False)

        # Try several methods, all should be clean
        methods_and_args = [
            ("target_success", ("test/path", 42, "units")),
            ("info", ("info message",)),
            ("warning", ("warning message",)),
            ("error", ("error message",)),
        ]

        for method_name, args in methods_and_args:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                method = getattr(terminal, method_name)
                method(*args)
                output = mock_stdout.getvalue()

                # Verify no ANSI codes (would be a bug)
                self.assertNotIn(
                    "\033[", output,
                    f"ANSI code found in {method_name} output: {output!r}"
                )

                # But actual text should still be there
                self.assertGreater(len(output.strip()), 0)

    def test_verbosity_quiet_suppresses_target_output(self) -> None:
        """QUIET mode suppresses basically everything (start, success, step, command)."""
        terminal = Terminal(verbosity=Verbosity.QUIET, use_color=False)

        suppressed_methods = [
            ("target_start", ("test/path",)),
            ("target_success", ("test/path", 42, "")),
            ("step", ("doing something",)),
            ("command", ("kubectl get pods",)),
        ]

        for method_name, args in suppressed_methods:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                method = getattr(terminal, method_name)
                method(*args)
                output = mock_stdout.getvalue()
                self.assertEqual(
                    output, "",
                    f"{method_name} should produce no output in QUIET mode"
                )

    def test_verbosity_normal_shows_targets_hides_commands(self) -> None:
        """NORMAL mode shows target info but hides command output."""
        terminal = Terminal(verbosity=Verbosity.NORMAL, use_color=False)

        # target_start and target_success do show up
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.target_start("test/path")
            output = mock_stdout.getvalue()
            self.assertGreater(len(output.strip()), 0)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.target_success("test/path", 42, "units")
            output = mock_stdout.getvalue()
            self.assertGreater(len(output.strip()), 0)

        # command and command_output are silent
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.command("kubectl get pods")
            output = mock_stdout.getvalue()
            self.assertEqual(output, "")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.command_output("output text")
            output = mock_stdout.getvalue()
            self.assertEqual(output, "")

    def test_verbosity_verbose_shows_commands(self) -> None:
        """VERBOSE mode shows command details (command + output)."""
        terminal = Terminal(verbosity=Verbosity.VERBOSE, use_color=False)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.command("kubectl get pods")
            output = mock_stdout.getvalue()
            self.assertGreater(len(output.strip()), 0)
            self.assertIn("kubectl", output)

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.command_output("pod1\npod2")
            output = mock_stdout.getvalue()
            self.assertGreater(len(output.strip()), 0)
            self.assertIn("pod1", output)

    def test_summary_format(self) -> None:
        """Summary output includes counts and failure error messages."""
        terminal = Terminal(verbosity=Verbosity.NORMAL, use_color=False)

        # Quick helper to make test DataPoints
        def make_dp(path: str) -> DataPoint:
            return DataPoint(
                path=path, value=0, unit="", description="test",
                raw_output="", metadata={},
            )

        # Mix of 3 successes and 1 failure
        results = [
            TargetResult(data_point=make_dp("a"), success=True, error=None, duration_seconds=1.0),
            TargetResult(data_point=make_dp("b"), success=True, error=None, duration_seconds=1.0),
            TargetResult(data_point=make_dp("c"), success=True, error=None, duration_seconds=1.0),
            TargetResult(data_point=None, success=False, error="Connection refused", duration_seconds=2.0),
        ]

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            terminal.summary(results)
            output = mock_stdout.getvalue()

        # Verify counts show up (total, passed, failed)
        self.assertIn("4", output)
        self.assertIn("3", output)
        self.assertIn("1", output)

        # Failure message should be in there too
        self.assertIn("Connection refused", output)

    def test_target_failure_output(self) -> None:
        """Failure output includes the ✗ icon, path, and error text."""
        output = self._capture_output(
            Verbosity.NORMAL, False,
            "target_failure", "databases/rabbitmq/status", "Connection refused"
        )

        self.assertIn("\u2717", output)  # ✗ failure icon
        self.assertIn("databases/rabbitmq/status", output)
        self.assertIn("Connection refused", output)

    def test_header_output(self) -> None:
        """Header should show the title text with box-drawing chars (═) for decoration."""
        output = self._capture_output(
            Verbosity.NORMAL, False,
            "header", "Wire Fact Gathering Tool"
        )

        self.assertIn("Wire Fact Gathering Tool", output)
        self.assertIn("\u2550", output)  # ═ box-drawing character


if __name__ == '__main__':
    unittest.main()
