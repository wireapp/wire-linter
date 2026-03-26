"""Unit tests for host target implementations.

Tests DiskUsage, MemoryUsage, CpuCount, LoadAverage, Uptime, and
NtpSynchronized targets. We mock out the run_command function that
run_local delegates to, then verify each target's collect() method
works as expected.
"""

from __future__ import annotations

from unittest.mock import patch, call

from src.lib.command import CommandResult
from src.lib.config import Config
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.host.disk_usage import DiskUsage
from src.targets.host.memory_usage import MemoryUsage
from src.targets.host.cpu_count import CpuCount
from src.targets.host.load_average import LoadAverage
from src.targets.host.uptime import Uptime
from src.targets.host.ntp_synchronized import NtpSynchronized
from src.targets.host.ntp_offset import NtpOffset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Just use the one helper from conftest. If it changes, we update it there
# and everything works. No copy-paste nightmares.
_make_config = make_minimal_config


def _make_terminal() -> Terminal:
    """Quiet terminal, no colors, keeps test output sane."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Logger that only shows errors, nothing else."""
    return Logger(level=LogLevel.ERROR)


def _cmd_result(stdout: str, command: str = "test") -> CommandResult:
    """Fake a successful command result with whatever stdout you want."""
    return CommandResult(
        command=command,
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.01,
        success=True,
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# DiskUsage
# ---------------------------------------------------------------------------

def test_disk_usage_description() -> None:
    """DiskUsage description should be «Root filesystem usage on admin host»."""
    target: DiskUsage = DiskUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Root filesystem usage on admin host"


def test_disk_usage_unit() -> None:
    """Unit should be a percentage sign."""
    target: DiskUsage = DiskUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "%"


def test_disk_usage_collect_parses_df_output() -> None:
    """Parse the Use% column from df output correctly."""
    df_output: str = (
        "Use%\n"
        " 60%\n"
    )
    target: DiskUsage = DiskUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(df_output)):
        result: int = target.collect()

    assert result == 60


def test_disk_usage_collect_low_usage() -> None:
    """Single-digit percentages work too."""
    df_output: str = (
        "Use%\n"
        "  3%\n"
    )
    target: DiskUsage = DiskUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(df_output)):
        result: int = target.collect()

    assert result == 3


def test_disk_usage_collect_full_disk() -> None:
    """100% usage should be handled fine."""
    df_output: str = (
        "Use%\n"
        "100%\n"
    )
    target: DiskUsage = DiskUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(df_output)):
        result: int = target.collect()

    assert result == 100


def test_disk_usage_execute_success() -> None:
    """execute() should return a TargetResult with the right value and unit."""
    df_output: str = (
        "Use%\n"
        " 50%\n"
    )
    target: DiskUsage = DiskUsage(_make_config(), _make_terminal(), _make_logger())
    target._path = "host/disk_usage"

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(df_output)):
        result = target.execute()

    assert result.success is True
    assert result.data_point.value == 50
    assert result.data_point.unit == "%"
    assert result.data_point.path == "host/disk_usage"


# ---------------------------------------------------------------------------
# MemoryUsage
# ---------------------------------------------------------------------------

def test_memory_usage_description() -> None:
    """Description should be «Memory usage on admin host»."""
    target: MemoryUsage = MemoryUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Memory usage on admin host"


def test_memory_usage_unit() -> None:
    """Unit is a percentage."""
    target: MemoryUsage = MemoryUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "%"


def test_memory_usage_collect_parses_free_output() -> None:
    """Parse free -b output and compute the usage percentage."""
    # 16 GiB total, 4 GiB available = 75% used
    total_bytes: int = 16 * (1024 ** 3)
    available_bytes: int = 4 * (1024 ** 3)
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        f"Mem:    {total_bytes}  {total_bytes - available_bytes}  1073741824  134217728  2147483648  {available_bytes}\n"
        "Swap:   4294967296           0  4294967296\n"
    )
    target: MemoryUsage = MemoryUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(free_output)):
        result: int = target.collect()

    assert result == 75


def test_memory_usage_collect_sets_dynamic_description() -> None:
    """Description should get enriched with actual GiB numbers."""
    # 8 GiB total, 2 GiB available = 6 GiB used, 75% usage
    total_bytes: int = 8 * (1024 ** 3)
    available_bytes: int = 2 * (1024 ** 3)
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        f"Mem:    {total_bytes}  {total_bytes - available_bytes}  1073741824  134217728  2147483648  {available_bytes}\n"
        "Swap:   0           0  0\n"
    )
    target: MemoryUsage = MemoryUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(free_output)):
        target.collect()

    assert target._dynamic_description == "Memory usage on admin host (6Gi used of 8Gi)"


def test_memory_usage_collect_zero_available() -> None:
    """When there's no available memory, that's 100% used."""
    total_bytes: int = 4 * (1024 ** 3)
    available_bytes: int = 0
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        f"Mem:    {total_bytes}  {total_bytes}  0  0  0  {available_bytes}\n"
        "Swap:   0           0  0\n"
    )
    target: MemoryUsage = MemoryUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(free_output)):
        result: int = target.collect()

    assert result == 100


# ---------------------------------------------------------------------------
# CpuCount
# ---------------------------------------------------------------------------

def test_cpu_count_description() -> None:
    """Description is «Number of CPU cores on admin host»."""
    target: CpuCount = CpuCount(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Number of CPU cores on admin host"


def test_cpu_count_unit() -> None:
    """Unit is «cores»."""
    target: CpuCount = CpuCount(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "cores"


def test_cpu_count_collect_parses_nproc() -> None:
    """Parse nproc output into an integer."""
    target: CpuCount = CpuCount(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result("8\n")):
        result: int = target.collect()

    assert result == 8


def test_cpu_count_collect_single_core() -> None:
    """Single core systems should work."""
    target: CpuCount = CpuCount(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result("1\n")):
        result: int = target.collect()

    assert result == 1


def test_cpu_count_collect_many_cores() -> None:
    """Big systems with lots of cores work too."""
    target: CpuCount = CpuCount(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result("128\n")):
        result: int = target.collect()

    assert result == 128


# ---------------------------------------------------------------------------
# LoadAverage
# ---------------------------------------------------------------------------

def test_load_average_description() -> None:
    """Description is «1-minute load average on admin host»."""
    target: LoadAverage = LoadAverage(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "1-minute load average on admin host"


def test_load_average_unit() -> None:
    """No unit for load average, it's unitless."""
    target: LoadAverage = LoadAverage(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_load_average_collect_parses_loadavg() -> None:
    """Extract the first field from /proc/loadavg."""
    loadavg_output: str = "0.42 0.38 0.35 2/520 12345\n"
    target: LoadAverage = LoadAverage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(loadavg_output)):
        result: float = target.collect()

    assert result == 0.42


def test_load_average_collect_high_load() -> None:
    """High load values should work."""
    loadavg_output: str = "15.67 12.34 10.00 5/800 99999\n"
    target: LoadAverage = LoadAverage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(loadavg_output)):
        result: float = target.collect()

    assert result == 15.67


def test_load_average_collect_zero_load() -> None:
    """Zero load is a thing too."""
    loadavg_output: str = "0.00 0.00 0.00 1/100 1234\n"
    target: LoadAverage = LoadAverage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(loadavg_output)):
        result: float = target.collect()

    assert result == 0.0


# ---------------------------------------------------------------------------
# Uptime
# ---------------------------------------------------------------------------

def test_uptime_description() -> None:
    """Description is «System uptime»."""
    target: Uptime = Uptime(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "System uptime"


def test_uptime_unit() -> None:
    """No unit for uptime either."""
    target: Uptime = Uptime(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_uptime_collect_strips_up_prefix() -> None:
    """Strip the «up » prefix if it's there."""
    target: Uptime = Uptime(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result("up 3 days, 4 hours, 12 minutes\n")):
        result: str = target.collect()

    assert result == "3 days, 4 hours, 12 minutes"


def test_uptime_collect_no_up_prefix() -> None:
    """Works fine if the prefix isn't there either."""
    target: Uptime = Uptime(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result("3 days, 4 hours\n")):
        result: str = target.collect()

    assert result == "3 days, 4 hours"


def test_uptime_collect_short_duration() -> None:
    """Short uptimes like «5 minutes» should parse."""
    target: Uptime = Uptime(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result("up 5 minutes\n")):
        result: str = target.collect()

    assert result == "5 minutes"


# ---------------------------------------------------------------------------
# NtpSynchronized
# ---------------------------------------------------------------------------

def test_ntp_synchronized_description() -> None:
    """Description is «System clock is synchronized via NTP»."""
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "System clock is synchronized via NTP"


def test_ntp_synchronized_unit() -> None:
    """No unit for boolean values."""
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_ntp_synchronized_collect_yes() -> None:
    """When NTPSynchronized=yes, return True."""
    show_output: str = "NTP=yes\nNTPSynchronized=yes\nTimeUSec=Thu 2025-01-01\n"
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(show_output)):
        result: bool = target.collect()

    assert result is True


def test_ntp_synchronized_collect_no() -> None:
    """When NTPSynchronized=no, return False."""
    show_output: str = "NTP=yes\nNTPSynchronized=no\nTimeUSec=Thu 2025-01-01\n"
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(show_output)):
        result: bool = target.collect()

    assert result is False


def test_ntp_synchronized_collect_fallback_to_status() -> None:
    """Fall back to timedatectl status if show doesn't have the NTPSynchronized key."""
    # First call (timedatectl show) missing the key
    show_output: str = "NTP=yes\nTimeUSec=Thu 2025-01-01\n"
    # Second call (timedatectl status) has what we need
    status_output: str = (
        "               Local time: Thu 2025-01-01 12:00:00 UTC\n"
        "           Universal time: Thu 2025-01-01 12:00:00 UTC\n"
        " System clock synchronized: yes\n"
        "              NTP service: active\n"
    )
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", side_effect=[
        _cmd_result(show_output),
        _cmd_result(status_output),
    ]):
        result: bool = target.collect()

    assert result is True


def test_ntp_synchronized_collect_fallback_not_synced() -> None:
    """Fallback also returns False when the system isn't synced."""
    show_output: str = "NTP=no\n"
    status_output: str = (
        "               Local time: Thu 2025-01-01 12:00:00 UTC\n"
        " System clock synchronized: no\n"
        "              NTP service: inactive\n"
    )
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", side_effect=[
        _cmd_result(show_output),
        _cmd_result(status_output),
    ]):
        result: bool = target.collect()

    assert result is False


def test_ntp_synchronized_collect_no_matching_lines() -> None:
    """If nothing matches, return False."""
    show_output: str = "NTP=yes\n"
    status_output: str = "Local time: Thu 2025-01-01 12:00:00 UTC\n"
    target: NtpSynchronized = NtpSynchronized(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", side_effect=[
        _cmd_result(show_output),
        _cmd_result(status_output),
    ]):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# NtpOffset
# ---------------------------------------------------------------------------

def test_ntp_offset_description() -> None:
    """Description is «Admin host NTP clock offset»."""
    target: NtpOffset = NtpOffset(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Admin host NTP clock offset"


def test_ntp_offset_unit() -> None:
    """Unit is milliseconds."""
    target: NtpOffset = NtpOffset(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "ms"


def test_ntp_offset_chronyc_rms_offset() -> None:
    """Parse the RMS offset from chronyc tracking output."""
    chronyc_output: str = (
        "Reference ID    : 10.0.0.1 (ntp.example.com)\n"
        "Stratum         : 3\n"
        "RMS offset      : 0.000013453 seconds\n"
        "Last offset     : +0.000008123 seconds\n"
    )
    target: NtpOffset = NtpOffset(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(chronyc_output)):
        result: float = target.collect()

    # 0.000013453 seconds = 0.013453 ms, rounded to 3 decimal places
    assert result == 0.013


def test_ntp_offset_chronyc_last_offset() -> None:
    """Fall back to Last offset when RMS isn't in the output."""
    chronyc_output: str = (
        "Reference ID    : 10.0.0.1\n"
        "Last offset     : -0.002500000 seconds\n"
    )
    target: NtpOffset = NtpOffset(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", return_value=_cmd_result(chronyc_output)):
        result: float = target.collect()

    # abs(-0.0025) * 1000 = 2.5 ms
    assert result == 2.5


def test_ntp_offset_fallback_to_ntpq() -> None:
    """Fall back to ntpq if chronyc isn't available."""
    chronyc_output: str = ""  # nothing from chronyc
    ntpq_output: str = (
        "     remote           refid      st t when poll reach   delay   offset  jitter\n"
        "==============================================================================\n"
        "*ntp.example.com .GPS.            1 u  123 1024  377    1.234   -3.456   0.789\n"
    )
    target: NtpOffset = NtpOffset(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", side_effect=[
        _cmd_result(chronyc_output),
        _cmd_result(ntpq_output),
    ]):
        result: float = target.collect()

    # ntpq offset column is already in ms, abs(-3.456) = 3.456
    assert result == 3.456


def test_ntp_offset_neither_available_raises() -> None:
    """Bail out if both chronyc and ntpq are a bust."""
    target: NtpOffset = NtpOffset(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.run_command", side_effect=[
        _cmd_result(""),  # chronyc empty
        _cmd_result(""),  # ntpq empty
    ]):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError as exc:
            assert "neither chronyc nor ntpq" in str(exc)
