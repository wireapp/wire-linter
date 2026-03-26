"""Tests for command execution (src/lib/command.py)."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from src.lib.command import CommandResult, run_command


class TestCommand(unittest.TestCase):
    """Test run_command with mocked subprocess."""

    def _make_mock_process(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        timeout_on_communicate: bool = False,
    ) -> MagicMock:
        """Build a mock Popen object with the given behavior.

        Args:
            stdout: What the process prints to stdout.
            stderr: What the process prints to stderr.
            returncode: Exit code to return.
            timeout_on_communicate: When True, first communicate() throws TimeoutExpired,
                second call returns empty (simulating kill).

        Returns:
            A configured MagicMock that looks like subprocess.Popen.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = returncode

        if timeout_on_communicate:
            # First call throws TimeoutExpired, second call (after kill) returns nothing
            mock_proc.communicate.side_effect = [
                subprocess.TimeoutExpired(cmd="test", timeout=30),
                (b"", b""),
            ]
        else:
            mock_proc.communicate.return_value = (
                stdout.encode("utf-8"),
                stderr.encode("utf-8"),
            )

        return mock_proc

    @patch("src.lib.command.subprocess.Popen")
    def test_successful_command(self, mock_popen: MagicMock) -> None:
        """Successful command gets exit_code=0 and success=True."""
        mock_proc = self._make_mock_process(
            stdout="hello world", stderr="", returncode=0
        )
        mock_popen.return_value = mock_proc

        result = run_command(["echo", "hello"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "hello world")
        self.assertIs(result.success, True)
        self.assertIs(result.timed_out, False)
        self.assertGreaterEqual(result.duration_seconds, 0)

    @patch("src.lib.command.subprocess.Popen")
    def test_failed_command(self, mock_popen: MagicMock) -> None:
        """Failed command gets success=False and non-zero exit code."""
        mock_proc = self._make_mock_process(
            stdout="", stderr="command not found", returncode=1
        )
        mock_popen.return_value = mock_proc

        result = run_command(["bad_cmd"])

        self.assertIs(result.success, False)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, "command not found")
        self.assertIs(result.timed_out, False)

    @patch("src.lib.command.subprocess.Popen")
    def test_command_timeout(self, mock_popen: MagicMock) -> None:
        """Timeout sets timed_out=True and success=False."""
        mock_proc = self._make_mock_process(timeout_on_communicate=True)
        mock_popen.return_value = mock_proc

        result = run_command(["sleep", "999"], timeout=1)

        self.assertIs(result.timed_out, True)
        self.assertIs(result.success, False)
        # Should've called kill() on the process to stop it
        mock_proc.kill.assert_called_once()

    @patch("src.lib.command.subprocess.Popen")
    def test_stderr_capture(self, mock_popen: MagicMock) -> None:
        """Capture stdout and stderr separately."""
        mock_proc = self._make_mock_process(
            stdout="output", stderr="warning message", returncode=0
        )
        mock_popen.return_value = mock_proc

        result = run_command(["cmd"])

        self.assertEqual(result.stdout, "output")
        self.assertEqual(result.stderr, "warning message")
        self.assertIs(result.success, True)

    @patch("src.lib.command.subprocess.Popen")
    def test_duration_tracking(self, mock_popen: MagicMock) -> None:
        """Track duration as a non-negative float."""
        mock_proc = self._make_mock_process(returncode=0)
        mock_popen.return_value = mock_proc

        result = run_command(["echo", "test"])

        self.assertGreaterEqual(result.duration_seconds, 0)
        self.assertIsInstance(result.duration_seconds, float)

    @patch("src.lib.command.subprocess.Popen")
    def test_command_string_field(self, mock_popen: MagicMock) -> None:
        """Command field has all the components we ran."""
        mock_proc = self._make_mock_process(returncode=0)
        mock_popen.return_value = mock_proc

        result = run_command(["kubectl", "get", "nodes", "-o", "json"])

        self.assertIn("kubectl", result.command)
        self.assertIn("get", result.command)
        self.assertIn("nodes", result.command)

    @patch("src.lib.command.subprocess.Popen")
    def test_popen_called_with_correct_args(self, mock_popen: MagicMock) -> None:
        """Popen called with right command and pipes for stdout/stderr."""
        mock_proc = self._make_mock_process(returncode=0)
        mock_popen.return_value = mock_proc

        run_command(["ls", "-la"], timeout=60)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args

        # Command list is the first positional arg
        self.assertEqual(call_args[0][0], ["ls", "-la"])

        # stdout and stderr should both be PIPE
        self.assertEqual(call_args[1]["stdout"], subprocess.PIPE)
        self.assertIn(call_args[1]["stderr"], (subprocess.PIPE, subprocess.STDOUT))


if __name__ == '__main__':
    unittest.main()
