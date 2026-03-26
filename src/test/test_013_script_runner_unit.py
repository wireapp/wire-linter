"""Tests for the script/runner.py CLI entry point.

Tests argument parsing for --config, --output, --target, --verbose, --quiet,
--no-color, --source, --parallel, and how they interact. Uses mocking to avoid
actually running anything.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from src.lib.terminal import Verbosity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_main(args: list[str]) -> int:
    """Run main() from script/runner with given CLI args.

    Patches sys.argv and the Runner class so we can see how main() turns CLI
    args into Runner constructor parameters.

    Args:
        args: CLI arguments (without the script name).

    Returns:
        Exit code that main() returns.
    """
    # Import inside helper so we don't hit side effects at module load time
    from src.script.runner import main

    full_argv: list[str] = ["runner.py"] + args

    with patch("sys.argv", full_argv):
        with patch("src.script.runner.Runner") as mock_runner_class:
            # Default: run() returns 0
            mock_instance = MagicMock()
            mock_instance.run.return_value = 0
            mock_runner_class.return_value = mock_instance

            exit_code: int = main()

    return exit_code


def _capture_runner_init(args: list[str]) -> dict:
    """Run main() and snag the kwargs passed to Runner().

    Args:
        args: CLI arguments (without the script name).

    Returns:
        Dict of kwargs passed to Runner constructor.
    """
    from src.script.runner import main

    full_argv: list[str] = ["runner.py"] + args

    with patch("sys.argv", full_argv):
        with patch("src.script.runner.Runner") as mock_runner_class:
            mock_instance = MagicMock()
            mock_instance.run.return_value = 0
            mock_runner_class.return_value = mock_instance

            main()

            # Grab the kwargs from the Runner() call
            call_kwargs: dict = mock_runner_class.call_args[1]

    return call_kwargs


# ---------------------------------------------------------------------------
# Required arguments
# ---------------------------------------------------------------------------

def test_main_required_args() -> None:
    """Check that main() passes --config and --output to Runner."""
    kwargs: dict = _capture_runner_init([
        "--config", "/path/to/config.yaml",
        "--output", "/path/to/output.jsonl",
    ])

    assert kwargs["config_path"] == "/path/to/config.yaml"
    assert kwargs["output_path"] == "/path/to/output.jsonl"


# ---------------------------------------------------------------------------
# --target argument
# ---------------------------------------------------------------------------

def test_main_target_default() -> None:
    """Check that --target defaults to «*»."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
    ])

    assert kwargs["target_pattern"] == "*"


def test_main_target_explicit() -> None:
    """Check that --target gets passed to Runner."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--target", "databases/cassandra/*",
    ])

    assert kwargs["target_pattern"] == "databases/cassandra/*"


# ---------------------------------------------------------------------------
# Verbosity flags
# ---------------------------------------------------------------------------

def test_main_default_verbosity() -> None:
    """Check that verbosity defaults to NORMAL."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
    ])

    assert kwargs["verbosity"] == Verbosity.NORMAL


def test_main_verbose_flag() -> None:
    """Check that --verbose sets verbosity to VERBOSE."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--verbose",
    ])

    assert kwargs["verbosity"] == Verbosity.VERBOSE


def test_main_quiet_flag() -> None:
    """Check that --quiet sets verbosity to QUIET."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--quiet",
    ])

    assert kwargs["verbosity"] == Verbosity.QUIET


def test_main_quiet_overrides_verbose() -> None:
    """Check that --quiet wins when both --quiet and --verbose are passed."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--quiet",
        "--verbose",
    ])

    assert kwargs["verbosity"] == Verbosity.QUIET


# ---------------------------------------------------------------------------
# --no-color flag
# ---------------------------------------------------------------------------

def test_main_color_default() -> None:
    """Check that color's on by default."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
    ])

    assert kwargs["use_color"] is True


def test_main_no_color_flag() -> None:
    """Check that --no-color turns off color."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--no-color",
    ])

    assert kwargs["use_color"] is False


# ---------------------------------------------------------------------------
# --source flag
# ---------------------------------------------------------------------------

def test_main_source_default() -> None:
    """Check that --source defaults to «admin-host»."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
    ])

    assert kwargs["gathered_from"] == "admin-host"


def test_main_source_admin_host() -> None:
    """Check that --source admin-host gets passed as gathered_from to Runner."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--source", "admin-host",
    ])

    assert kwargs["gathered_from"] == "admin-host"


def test_main_source_ssh_into_admin_host() -> None:
    """Check that --source ssh-into-admin-host gets passed as gathered_from to Runner."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--source", "ssh-into-admin-host",
    ])

    assert kwargs["gathered_from"] == "ssh-into-admin-host"


def test_main_source_client() -> None:
    """Check that --source client gets passed as gathered_from to Runner."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--source", "client",
    ])

    assert kwargs["gathered_from"] == "client"
    assert kwargs["source_type"] == "client"


# ---------------------------------------------------------------------------
# --parallel flag
# ---------------------------------------------------------------------------

def test_main_parallel_default() -> None:
    """Check that --parallel defaults to 1 (sequential mode)."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
    ])

    assert kwargs["parallel"] == 1


def test_main_parallel_flag() -> None:
    """Check that --parallel N gets passed to Runner as the parallel kwarg."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--parallel", "4",
    ])

    assert kwargs["parallel"] == 4


def test_main_parallel_clamped_to_one() -> None:
    """Check that --parallel 0 gets clamped to 1 via max(1, args.parallel)."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--parallel", "0",
    ])

    assert kwargs["parallel"] == 1


# ---------------------------------------------------------------------------
# --dry-run flag
# ---------------------------------------------------------------------------

def test_main_dry_run_default() -> None:
    """Check that --dry-run defaults to False."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
    ])

    assert kwargs["dry_run"] is False


def test_main_dry_run_flag() -> None:
    """Check that --dry-run gets passed to Runner."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--output", "o.jsonl",
        "--dry-run",
    ])

    assert kwargs["dry_run"] is True


def test_main_dry_run_without_output() -> None:
    """Check that --dry-run doesn't require --output."""
    kwargs: dict = _capture_runner_init([
        "--config", "c.yaml",
        "--dry-run",
    ])

    assert kwargs["dry_run"] is True
    assert kwargs["output_path"] == ""


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

def test_main_returns_runner_exit_code() -> None:
    """Check that main() returns whatever Runner.run() gives back."""
    from src.script.runner import main

    full_argv: list[str] = [
        "runner.py", "--config", "c.yaml", "--output", "o.jsonl",
    ]

    with patch("sys.argv", full_argv):
        with patch("src.script.runner.Runner") as mock_runner_class:
            mock_instance = MagicMock()
            mock_instance.run.return_value = 2
            mock_runner_class.return_value = mock_instance

            exit_code: int = main()

    assert exit_code == 2
