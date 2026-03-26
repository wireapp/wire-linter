"""OS target tests: OsVersion, KubenodeNtp, UnprivilegedPortStart.

All are PerHostTarget subclasses, so we test collect_for_host() and get_hosts() separately."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.lib.config import Config, NodesConfig
from src.test.conftest import make_minimal_config
from src.targets.os.version import OsVersion
from src.targets.os.kubenode_ntp import KubenodeNtp
from src.targets.os.unprivileged_port_start import UnprivilegedPortStart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terminal() -> Terminal:
    """Silent terminal for cleaner test output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Logger that only shows errors."""
    return Logger(level=LogLevel.ERROR)


def _ssh_cmd_result(stdout: str) -> CommandResult:
    """Make a successful SSH command result."""
    return CommandResult(
        command="ssh test",
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )


def _kubectl_cmd_result(stdout: str = "{}") -> CommandResult:
    """Make a successful kubectl command result."""
    return CommandResult(
        command="kubectl get",
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# OsVersion
# ---------------------------------------------------------------------------

def test_os_version_description() -> None:
    """OsVersion description looks right."""
    target: OsVersion = OsVersion(make_minimal_config(), _make_terminal(), _make_logger())
    assert "os" in target.description.lower()


def test_os_version_collect_for_host_ubuntu() -> None:
    """Parse Ubuntu correctly from /etc/os-release."""
    os_release: str = (
        'NAME="Ubuntu"\n'
        'VERSION="24.04.1 LTS (Noble Numbat)"\n'
        'PRETTY_NAME="Ubuntu 24.04.1 LTS"\n'
        'VERSION_ID="24.04"\n'
    )
    host: dict[str, str] = {"name": "kubenode-10.0.0.5", "ip": "10.0.0.5"}
    target: OsVersion = OsVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(os_release)):
        result: str = target.collect_for_host(host)

    assert result == "Ubuntu 24.04.1 LTS"


def test_os_version_collect_for_host_unsupported() -> None:
    """Flag unsupported OS versions."""
    os_release: str = (
        'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\n'
        'VERSION_ID="12"\n'
    )
    host: dict[str, str] = {"name": "datanode-10.0.0.6", "ip": "10.0.0.6"}
    target: OsVersion = OsVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(os_release)):
        result: str = target.collect_for_host(host)

    assert "Debian" in result
    # Health info should note it's not in supported versions
    assert "not tested with Wire" in target._health_info


def test_os_version_collect_for_host_no_pretty_name_raises() -> None:
    """Blow up when PRETTY_NAME is missing."""
    host: dict[str, str] = {"name": "node-1", "ip": "10.0.0.5"}
    target: OsVersion = OsVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("ID=unknown\n")):
        try:
            target.collect_for_host(host)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# KubenodeNtp
# ---------------------------------------------------------------------------

def test_kubenode_ntp_description() -> None:
    """KubenodeNtp description looks right."""
    target: KubenodeNtp = KubenodeNtp(make_minimal_config(), _make_terminal(), _make_logger())
    assert "ntp" in target.description.lower()


def test_kubenode_ntp_collect_for_host_synced() -> None:
    """Return True when NTPSynchronized=yes."""
    host: dict[str, str] = {"name": "kubenode-10.0.0.5", "ip": "10.0.0.5"}
    target: KubenodeNtp = KubenodeNtp(make_minimal_config(), _make_terminal(), _make_logger())

    timedatectl_output: str = "NTPSynchronized=yes\nNTP=yes\n"
    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(timedatectl_output)):
        result: bool = target.collect_for_host(host)

    assert result is True


def test_kubenode_ntp_collect_for_host_not_synced() -> None:
    """Return False when NTPSynchronized=no."""
    host: dict[str, str] = {"name": "kubenode-10.0.0.5", "ip": "10.0.0.5"}
    target: KubenodeNtp = KubenodeNtp(make_minimal_config(), _make_terminal(), _make_logger())

    timedatectl_output: str = "NTPSynchronized=no\nNTP=no\n"
    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(timedatectl_output)):
        result: bool = target.collect_for_host(host)

    assert result is False


def test_kubenode_ntp_collect_for_host_fallback_format() -> None:
    """Handle the human-readable timedatectl format."""
    host: dict[str, str] = {"name": "kubenode-10.0.0.5", "ip": "10.0.0.5"}
    target: KubenodeNtp = KubenodeNtp(make_minimal_config(), _make_terminal(), _make_logger())

    timedatectl_output: str = (
        "               Local time: Thu 2026-03-14 12:00:00 UTC\n"
        " System clock synchronized: yes\n"
    )
    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(timedatectl_output)):
        result: bool = target.collect_for_host(host)

    assert result is True


def test_kubenode_ntp_get_hosts_from_config() -> None:
    """Use config.nodes.kube_nodes when set."""
    config: Config = make_minimal_config()
    config.nodes = NodesConfig(kube_nodes=["10.0.0.1", "10.0.0.2"], data_nodes=[])
    target: KubenodeNtp = KubenodeNtp(config, _make_terminal(), _make_logger())

    hosts: list[dict[str, str]] = target.get_hosts()

    assert len(hosts) == 2
    assert hosts[0]["ip"] == "10.0.0.1"
    assert hosts[0]["name"] == "kubenode-10.0.0.1"


# ---------------------------------------------------------------------------
# UnprivilegedPortStart
# ---------------------------------------------------------------------------

def test_unprivileged_port_start_description() -> None:
    """UnprivilegedPortStart description looks right."""
    target: UnprivilegedPortStart = UnprivilegedPortStart(make_minimal_config(), _make_terminal(), _make_logger())
    assert "unprivileged" in target.description.lower()


def test_unprivileged_port_start_collect_for_host_ok() -> None:
    """Value <= 443 is healthy."""
    host: dict[str, str] = {"name": "node-1", "ip": "10.0.0.5"}
    target: UnprivilegedPortStart = UnprivilegedPortStart(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("0")):
        result: int = target.collect_for_host(host)

    assert result == 0
    assert "can bind" in target._health_info


def test_unprivileged_port_start_collect_for_host_too_high() -> None:
    """Flag values > 443."""
    host: dict[str, str] = {"name": "node-1", "ip": "10.0.0.5"}
    target: UnprivilegedPortStart = UnprivilegedPortStart(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("1024")):
        result: int = target.collect_for_host(host)

    assert result == 1024
    assert "PROBLEM" in target._health_info


def test_unprivileged_port_start_collect_for_host_not_found_raises() -> None:
    """Blow up when sysctl returns not_found."""
    host: dict[str, str] = {"name": "node-1", "ip": "10.0.0.5"}
    target: UnprivilegedPortStart = UnprivilegedPortStart(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("not_found")):
        try:
            target.collect_for_host(host)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass
