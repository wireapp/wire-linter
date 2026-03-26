"""Tests for operations checks: backups, log rotation, monitoring, and SMTP.

These watch over infrastructure maintenance tasks; making sure backups aren't stale,
logs get rotated properly, monitoring stack is available, and we can send alerts.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.operations.backup_freshness import BackupFreshness
from src.targets.operations.log_rotation import LogRotation
from src.targets.operations.monitoring_stack import MonitoringStack
from src.targets.operations.smtp_service import SmtpService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terminal() -> Terminal:
    """Quiet terminal for tests; no noise in output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Logger that only shows errors; quiet for tests."""
    return Logger(level=LogLevel.ERROR)


def _ssh_cmd_result(stdout: str) -> CommandResult:
    """Successful SSH command result with given output."""
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
    """Successful kubectl command result with given JSON output."""
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
# BackupFreshness
# ---------------------------------------------------------------------------

def test_backup_freshness_description() -> None:
    """Should mention backups in the description."""
    target: BackupFreshness = BackupFreshness(make_minimal_config(), _make_terminal(), _make_logger())
    assert "backup" in target.description.lower()


def test_backup_freshness_recent() -> None:
    """Fresh backup from a few minutes ago; should report «recent»."""
    ls_output: str = "-rw-r--r-- 1 root root 1234 Mar 14 12:00 backup-2026.tar.gz\n"
    target: BackupFreshness = BackupFreshness(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result(ls_output),
        _ssh_cmd_result("/var/backups/x\nRECENT"),
    ]):
        result: str = target.collect()

    assert "recent" in result.lower()


def test_backup_freshness_no_backups() -> None:
    """No backups exist at all; should report «no backups found»."""
    target: BackupFreshness = BackupFreshness(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result("NO_BACKUPS_FOUND"),
        _ssh_cmd_result(""),
    ]):
        result: str = target.collect()

    assert "no backups" in result.lower()


def test_backup_freshness_old() -> None:
    """Backup from January; way too old. Should report «old»."""
    ls_output: str = "-rw-r--r-- 1 root root 1234 Jan 01 12:00 backup-old.tar.gz\n"
    target: BackupFreshness = BackupFreshness(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result(ls_output),
        _ssh_cmd_result("OLD_OR_MISSING"),
    ]):
        result: str = target.collect()

    assert "old" in result.lower()


# ---------------------------------------------------------------------------
# LogRotation
# ---------------------------------------------------------------------------

def test_log_rotation_description() -> None:
    """Should mention log rotation."""
    target: LogRotation = LogRotation(make_minimal_config(), _make_terminal(), _make_logger())
    assert "log rotation" in target.description.lower()


def test_log_rotation_compliant() -> None:
    """Maxage is 3 days, meets policy; should report «compliant»."""
    logrotate_output: str = (
        "/var/log/nginx/*.log {\n"
        "    daily\n"
        "    rotate 3\n"
        "    maxage 3\n"
        "    compress\n"
        "}\n"
    )
    target: LogRotation = LogRotation(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(logrotate_output)):
        result: str = target.collect()

    assert "compliant" in result.lower()


def test_log_rotation_exceeds_policy() -> None:
    """Maxage is 30 days; way too long. Should report «exceeds»."""
    logrotate_output: str = "maxage 30\nrotate 30\ndaily\n"
    target: LogRotation = LogRotation(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(logrotate_output)):
        result: str = target.collect()

    assert "exceeds" in result.lower()


def test_log_rotation_not_configured() -> None:
    """No logrotate config found; should report «not configured»."""
    target: LogRotation = LogRotation(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        result: str = target.collect()

    assert "not configured" in result.lower()


# ---------------------------------------------------------------------------
# MonitoringStack
# ---------------------------------------------------------------------------

def test_monitoring_stack_description() -> None:
    """Should mention monitoring in the description."""
    target: MonitoringStack = MonitoringStack(make_minimal_config(), _make_terminal(), _make_logger())
    assert "monitoring" in target.description.lower()


def test_monitoring_stack_running() -> None:
    """Prometheus and Grafana both running; we're good."""
    pods_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "prometheus-server-0"}, "status": {"phase": "Running"}},
        {"metadata": {"name": "grafana-abc123"}, "status": {"phase": "Running"}},
    ]}
    target: MonitoringStack = MonitoringStack(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), pods_data)):
        result: bool = target.collect()

    assert result is True


def test_monitoring_stack_not_running() -> None:
    """No monitoring pods anywhere; should fail."""
    empty: dict[str, Any] = {"items": []}
    target: MonitoringStack = MonitoringStack(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), empty),
        (_kubectl_cmd_result(), empty),
    ]):
        result: bool = target.collect()

    assert result is False


def test_monitoring_stack_in_different_namespace() -> None:
    """Monitoring deployed in a custom namespace; we find it on second lookup."""
    empty: dict[str, Any] = {"items": []}
    all_ns_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "prometheus-kube-0"}, "status": {"phase": "Running"}},
    ]}
    target: MonitoringStack = MonitoringStack(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), empty),
        (_kubectl_cmd_result(), all_ns_data),
    ]):
        result: bool = target.collect()

    assert result is True


# ---------------------------------------------------------------------------
# SmtpService
# ---------------------------------------------------------------------------

def test_smtp_service_description() -> None:
    """Should mention SMTP."""
    target: SmtpService = SmtpService(make_minimal_config(), _make_terminal(), _make_logger())
    assert "smtp" in target.description.lower()


def test_smtp_service_running() -> None:
    """SMTP relay pod is running; we can send mail."""
    pods_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "smtp-relay-0"}, "status": {"phase": "Running"}},
    ]}
    target: SmtpService = SmtpService(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), pods_data)):
        result: bool = target.collect()

    assert result is True


def test_smtp_service_fake_aws_sns() -> None:
    """«fake-aws-sns» pod works as an SMTP alternative; that's fine too."""
    pods_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "fake-aws-sns-0"}, "status": {"phase": "Running"}},
    ]}
    target: SmtpService = SmtpService(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), pods_data)):
        result: bool = target.collect()

    assert result is True


def test_smtp_service_not_running() -> None:
    """Only Brig running, no SMTP; should fail."""
    pods_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig-0"}, "status": {"phase": "Running"}},
    ]}
    target: SmtpService = SmtpService(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), pods_data)):
        result: bool = target.collect()

    assert result is False
