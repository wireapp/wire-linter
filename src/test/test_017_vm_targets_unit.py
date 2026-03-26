"""Unit tests for VM target implementations.

Tests VmDiskUsage, VmLoadAverage, VmMemoryUsed, VmDiskTotal, and VmMemoryTotal.
We mock run_ssh_command in the SSH layer to test each target's collect_for_host()
method. Also testing that get_hosts() properly delegates to discover_vm_hosts.
"""

from __future__ import annotations

from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.config import Config
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.targets.vm.disk_usage import VmDiskUsage
from src.targets.vm.disk_total import VmDiskTotal
from src.targets.vm.load_average import VmLoadAverage
from src.targets.vm.memory_total import VmMemoryTotal
from src.targets.vm.memory_used import VmMemoryUsed
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> Config:
    """Spin up a minimal Config for testing.

    We use make_minimal_config() so we don't have to maintain two copies
    of required fields as Config evolves.
    """
    return make_minimal_config()


def _make_terminal() -> Terminal:
    """Set up a quiet terminal to keep test output clean."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Create a logger that silences most stuff."""
    return Logger(level=LogLevel.ERROR)


def _cmd_result(stdout: str, command: str = "test") -> CommandResult:
    """Make a successful CommandResult with the given stdout."""
    return CommandResult(
        command=command,
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.01,
        success=True,
        timed_out=False,
    )


def _ssh_cmd_result(stdout: str) -> CommandResult:
    """Make a successful CommandResult for SSH output."""
    return CommandResult(
        command="ssh test",
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )


SAMPLE_HOST: dict[str, str] = {"name": "kubenode1", "ip": "192.168.1.10"}


# ---------------------------------------------------------------------------
# VmDiskUsage
# ---------------------------------------------------------------------------

def test_vm_disk_usage_description() -> None:
    """Check that VmDiskUsage has the right description."""
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Disk usage"


def test_vm_disk_usage_unit() -> None:
    """Check that VmDiskUsage reports percentage unit."""
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "%"


def test_vm_disk_usage_is_per_host() -> None:
    """Check that VmDiskUsage is a per-host target."""
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())
    assert target.is_per_host is True


def test_vm_disk_usage_collect_for_host_parses_df() -> None:
    """Check that VmDiskUsage parses df output correctly."""
    df_output: str = "/dev/sda1        50G   30G   20G  60% /\n"
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(df_output)):
        result: int = target.collect_for_host(SAMPLE_HOST)

    assert result == 60


def test_vm_disk_usage_collect_for_host_single_digit() -> None:
    """Check that VmDiskUsage handles single-digit percentages."""
    df_output: str = "/dev/sda1       100G   3G   97G   3% /\n"
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(df_output)):
        result: int = target.collect_for_host(SAMPLE_HOST)

    assert result == 3


def test_vm_disk_usage_collect_for_host_full_disk() -> None:
    """Check that VmDiskUsage handles a fully used disk."""
    df_output: str = "/dev/sda1        50G   50G     0G 100% /\n"
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(df_output)):
        result: int = target.collect_for_host(SAMPLE_HOST)

    assert result == 100


def test_vm_disk_usage_description_for_host() -> None:
    """Check that VmDiskUsage generates the right per-host description."""
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())
    desc: str = target.description_for_host(SAMPLE_HOST)

    assert desc == "Disk usage on kubenode1 (192.168.1.10)"


def test_vm_disk_usage_get_hosts_delegates() -> None:
    """Check that VmDiskUsage.get_hosts() calls discover_vm_hosts."""
    target: VmDiskUsage = VmDiskUsage(_make_config(), _make_terminal(), _make_logger())
    mock_hosts: list[dict[str, str]] = [{"name": "mock1", "ip": "1.2.3.4"}]

    with patch("src.targets.vm.disk_usage.discover_vm_hosts", return_value=mock_hosts):
        hosts: list[dict[str, str]] = target.get_hosts()

    assert hosts == mock_hosts


# ---------------------------------------------------------------------------
# VmLoadAverage
# ---------------------------------------------------------------------------

def test_vm_load_average_description() -> None:
    """Check that VmLoadAverage has the right description."""
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "1-minute load average"


def test_vm_load_average_unit() -> None:
    """Check that VmLoadAverage reports an empty unit."""
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_vm_load_average_is_per_host() -> None:
    """Check that VmLoadAverage is a per-host target."""
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())
    assert target.is_per_host is True


def test_vm_load_average_collect_for_host_parses_loadavg() -> None:
    """Check that VmLoadAverage parses /proc/loadavg correctly."""
    loadavg_output: str = "0.42 0.38 0.35 2/520 12345\n"
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(loadavg_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 0.42


def test_vm_load_average_collect_for_host_high_load() -> None:
    """Check that VmLoadAverage handles high load correctly."""
    loadavg_output: str = "15.67 12.34 10.00 5/800 99999\n"
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(loadavg_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 15.67


def test_vm_load_average_collect_for_host_zero() -> None:
    """Check that VmLoadAverage handles zero load."""
    loadavg_output: str = "0.00 0.00 0.00 1/100 1234\n"
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(loadavg_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 0.0


def test_vm_load_average_description_for_host() -> None:
    """Check that VmLoadAverage generates the right per-host description."""
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())
    desc: str = target.description_for_host(SAMPLE_HOST)

    assert desc == "1-minute load average on kubenode1"


def test_vm_load_average_get_hosts_delegates() -> None:
    """Check that VmLoadAverage.get_hosts() calls discover_vm_hosts."""
    target: VmLoadAverage = VmLoadAverage(_make_config(), _make_terminal(), _make_logger())
    mock_hosts: list[dict[str, str]] = [{"name": "mock1", "ip": "1.2.3.4"}]

    with patch("src.targets.vm.load_average.discover_vm_hosts", return_value=mock_hosts):
        hosts: list[dict[str, str]] = target.get_hosts()

    assert hosts == mock_hosts


# ---------------------------------------------------------------------------
# VmMemoryUsed
# ---------------------------------------------------------------------------

def test_vm_memory_used_description() -> None:
    """Check that VmMemoryUsed has the right description."""
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Memory used"


def test_vm_memory_used_unit() -> None:
    """Check that VmMemoryUsed reports Gi unit."""
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "Gi"


def test_vm_memory_used_is_per_host() -> None:
    """Check that VmMemoryUsed is a per-host target."""
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())
    assert target.is_per_host is True


def test_vm_memory_used_collect_for_host_parses_free() -> None:
    """Check that VmMemoryUsed parses free output and converts to GiB."""
    # 8192 MB used = 8.0 Gi
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:          16384        8192        4096         256        4096        8192\n"
        "Swap:          4096           0        4096\n"
    )
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(free_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 8.0


def test_vm_memory_used_collect_for_host_fractional_gi() -> None:
    """Check that VmMemoryUsed rounds to one decimal place."""
    # 3500 MB used = 3500/1024 = 3.41796875, rounds to 3.4 Gi
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:          16384        3500       10000         256        2684       12884\n"
        "Swap:          4096           0        4096\n"
    )
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(free_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 3.4


def test_vm_memory_used_collect_for_host_low_memory() -> None:
    """Check that VmMemoryUsed handles small memory values."""
    # 512 MB used = 0.5 Gi
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:           4096         512        2500         100        1084        3584\n"
        "Swap:          2048           0        2048\n"
    )
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(free_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 0.5


def test_vm_memory_used_collect_for_host_zero_used() -> None:
    """Check that VmMemoryUsed handles zero memory used."""
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:           4096           0        4096           0           0        4096\n"
        "Swap:             0           0           0\n"
    )
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_cmd_result(free_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 0.0


def test_vm_memory_used_description_for_host() -> None:
    """Check that VmMemoryUsed generates the right per-host description."""
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())
    desc: str = target.description_for_host(SAMPLE_HOST)

    assert desc == "Memory used on kubenode1"


def test_vm_memory_used_get_hosts_delegates() -> None:
    """Check that VmMemoryUsed.get_hosts() calls discover_vm_hosts."""
    target: VmMemoryUsed = VmMemoryUsed(_make_config(), _make_terminal(), _make_logger())
    mock_hosts: list[dict[str, str]] = [{"name": "mock1", "ip": "1.2.3.4"}]

    with patch("src.targets.vm.memory_used.discover_vm_hosts", return_value=mock_hosts):
        hosts: list[dict[str, str]] = target.get_hosts()

    assert hosts == mock_hosts


# ---------------------------------------------------------------------------
# VmDiskTotal
# ---------------------------------------------------------------------------

def test_vm_disk_total_description() -> None:
    """Check that VmDiskTotal has the right description."""
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Disk total"


def test_vm_disk_total_unit() -> None:
    """Check that VmDiskTotal reports Gi unit."""
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "Gi"


def test_vm_disk_total_collect_for_host_parses_df() -> None:
    """Check that VmDiskTotal parses df output and converts to GiB."""
    df_output: str = "/dev/sda2       102400M   51200M   51200M  50% /\n"
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(df_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 100.0


def test_vm_disk_total_collect_for_host_small_disk() -> None:
    """Check that VmDiskTotal handles smaller disks."""
    df_output: str = "/dev/sda2       51200M   25600M   25600M  50% /\n"
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(df_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 50.0


def test_vm_disk_total_collect_for_host_raises_on_insufficient_fields() -> None:
    """Check that VmDiskTotal raises on bad df output."""
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        try:
            target.collect_for_host(SAMPLE_HOST)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_vm_disk_total_description_for_host() -> None:
    """Check that VmDiskTotal generates the right per-host description."""
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())
    desc: str = target.description_for_host(SAMPLE_HOST)

    assert desc == "Total disk on kubenode1"


def test_vm_disk_total_get_hosts_delegates() -> None:
    """Check that VmDiskTotal.get_hosts() calls discover_vm_hosts."""
    target: VmDiskTotal = VmDiskTotal(_make_config(), _make_terminal(), _make_logger())
    mock_hosts: list[dict[str, str]] = [{"name": "mock1", "ip": "1.2.3.4"}]

    with patch("src.targets.vm.disk_total.discover_vm_hosts", return_value=mock_hosts):
        hosts: list[dict[str, str]] = target.get_hosts()

    assert hosts == mock_hosts


# ---------------------------------------------------------------------------
# VmMemoryTotal
# ---------------------------------------------------------------------------

def test_vm_memory_total_description() -> None:
    """Check that VmMemoryTotal has the right description."""
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Memory total"


def test_vm_memory_total_unit() -> None:
    """Check that VmMemoryTotal reports Gi unit."""
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "Gi"


def test_vm_memory_total_collect_for_host_parses_free() -> None:
    """Check that VmMemoryTotal parses free output and converts to GiB."""
    free_output: str = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:          16384        8192        4096         256        4096       12288\n"
        "Swap:          2048           0        2048\n"
    )
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(free_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 16.0


def test_vm_memory_total_collect_for_host_fractional() -> None:
    """Check that VmMemoryTotal handles fractional GiB values."""
    free_output: str = (
        "              total        used        free\n"
        "Mem:           7680        4096        3584\n"
    )
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(free_output)):
        result: float = target.collect_for_host(SAMPLE_HOST)

    assert result == 7.5


def test_vm_memory_total_collect_for_host_no_mem_line_raises() -> None:
    """Check that VmMemoryTotal raises when Mem: line is missing."""
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("Swap: 2048 0 2048\n")):
        try:
            target.collect_for_host(SAMPLE_HOST)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_vm_memory_total_description_for_host() -> None:
    """Check that VmMemoryTotal generates the right per-host description."""
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())
    desc: str = target.description_for_host(SAMPLE_HOST)

    assert desc == "Total memory on kubenode1"


def test_vm_memory_total_get_hosts_delegates() -> None:
    """Check that VmMemoryTotal.get_hosts() calls discover_vm_hosts."""
    target: VmMemoryTotal = VmMemoryTotal(_make_config(), _make_terminal(), _make_logger())
    mock_hosts: list[dict[str, str]] = [{"name": "mock1", "ip": "1.2.3.4"}]

    with patch("src.targets.vm.memory_total.discover_vm_hosts", return_value=mock_hosts):
        hosts: list[dict[str, str]] = target.get_hosts()

    assert hosts == mock_hosts
