"""Runs local commands as subprocesses, captures output, handles timeouts.

This is the foundation for SSH, kubectl, database CLI wrappers, etc.
"""

from __future__ import annotations

import subprocess
import time
import os
import shlex
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Everything that came back from running a command."""

    command: str              # original command string, kept for logs
    exit_code: int            # process exit code
    stdout: str               # standard output
    stderr: str               # standard error
    duration_seconds: float   # wall-clock time
    success: bool             # True if exit_code == 0
    timed_out: bool           # True if we killed it due to timeout
    stdout_raw: bytes = b''   # raw bytes before UTF-8 decoding, for binary protocols


def run_command(
    command: list[str],
    timeout: int = 30,
    capture_stderr: bool = True,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    stdin_data: bytes | None = None,
) -> CommandResult:
    """Run a local command and return its output.

    Kills it if it goes past the timeout.

    Args:
        command: Command + args as a list (e.g. ['kubectl', 'get', 'nodes']).
        timeout: Seconds before killing it.
        capture_stderr: Capture stderr separately, or fold it into stdout.
        env: Extra env vars to set (merged into current environment).
        cwd: Working directory for the subprocess.
        stdin_data: Raw bytes to send to the process's stdin (e.g. for binary
            protocol probes). When provided, stdin is piped and closed after
            writing; stdout_raw on the result carries the raw response bytes.

    Returns:
        CommandResult with stdout, stderr, exit code, duration, and timeout flag.
    """
    # string version for logging
    command_str: str = shlex.join(command)

    # how long does this take
    start_time: float = time.monotonic()

    # merge extra env vars into current environment
    merged_env: dict[str, str] | None = None
    if env is not None:
        merged_env = os.environ.copy()
        merged_env.update(env)

    # where does stderr go
    stderr_target: int = subprocess.PIPE if capture_stderr else subprocess.STDOUT

    # pipe stdin when we need to feed data into the process (binary probes etc.)
    stdin_target: int | None = subprocess.PIPE if stdin_data is not None else None

    # start the subprocess
    try:
        proc: subprocess.Popen[bytes] = subprocess.Popen(
            command,
            stdin=stdin_target,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
            env=merged_env,
            cwd=cwd,
        )
    except FileNotFoundError:
        # binary not on PATH
        duration: float = time.monotonic() - start_time
        return CommandResult(
            command=command_str,
            exit_code=-1,
            stdout='',
            stderr=f"Command not found: {command[0]}",
            duration_seconds=duration,
            success=False,
            timed_out=False,
        )
    except OSError as exc:
        # permission denied, etc.
        duration = time.monotonic() - start_time
        return CommandResult(
            command=command_str,
            exit_code=-1,
            stdout='',
            stderr=str(exc),
            duration_seconds=duration,
            success=False,
            timed_out=False,
        )

    try:
        stdout_bytes, stderr_bytes = proc.communicate(
            input=stdin_data, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # stuck, kill it
        proc.kill()
        # drain remaining output
        stdout_bytes, stderr_bytes = proc.communicate()

        duration: float = time.monotonic() - start_time

        return CommandResult(
            command=command_str,
            exit_code=-1,
            stdout=stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else '',
            stderr=(stderr_bytes or b'').decode('utf-8', errors='replace') if capture_stderr else '',
            duration_seconds=duration,
            success=False,
            timed_out=True,
            stdout_raw=stdout_bytes or b'',
        )

    # normal case
    duration = time.monotonic() - start_time

    return CommandResult(
        command=command_str,
        exit_code=proc.returncode,
        stdout=stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else '',
        stderr=(stderr_bytes or b'').decode('utf-8', errors='replace') if capture_stderr else '',
        duration_seconds=duration,
        success=(proc.returncode == 0),
        timed_out=False,
        stdout_raw=stdout_bytes or b'',
    )
