"""Tests for secrets and migrations: making sure required K8s secrets exist and migration jobs finish.

Both are infrastructure sanity checks; if secrets are missing, deployments can't start,
and if migrations fail, data consistency is compromised.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.secrets.required_present import RequiredSecretsPresent
from src.targets.migrations.jobs_completed import MigrationJobsCompleted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terminal() -> Terminal:
    """Quiet terminal for tests; no noise in output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Logger that only shows errors; quiet for tests."""
    return Logger(level=LogLevel.ERROR)


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
# RequiredSecretsPresent
# ---------------------------------------------------------------------------

def test_required_secrets_description() -> None:
    """Should mention secrets in the description."""
    target: RequiredSecretsPresent = RequiredSecretsPresent(make_minimal_config(), _make_terminal(), _make_logger())
    assert "secret" in target.description.lower()


def test_required_secrets_all_present() -> None:
    """All four required secrets exist with data; should pass."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig-secrets"}, "data": {"zauth-key": "abc"}},
        {"metadata": {"name": "nginz-secrets"}, "data": {"zauth-pub": "def"}},
        {"metadata": {"name": "brig-turn"}, "data": {"turn-secret.txt": "ghi"}},
        {"metadata": {"name": "wire-server-tls"}, "data": {"tls.crt": "cert", "tls.key": "key"}},
    ]}
    target: RequiredSecretsPresent = RequiredSecretsPresent(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is True


def test_required_secrets_missing_brig() -> None:
    """«brig-secrets» is gone; should fail."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "nginz-secrets"}, "data": {"zauth-pub": "def"}},
        {"metadata": {"name": "brig-turn"}, "data": {"turn-secret.txt": "ghi"}},
        {"metadata": {"name": "wire-server-tls"}, "data": {"tls.crt": "cert", "tls.key": "key"}},
    ]}
    target: RequiredSecretsPresent = RequiredSecretsPresent(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is False


def test_required_secrets_empty_secret() -> None:
    """«brig-secrets» exists but has no data; should fail."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig-secrets"}, "data": {}},
        {"metadata": {"name": "nginz-secrets"}, "data": {"zauth-pub": "def"}},
        {"metadata": {"name": "brig-turn"}, "data": {"turn-secret.txt": "ghi"}},
        {"metadata": {"name": "wire-server-tls"}, "data": {"tls.crt": "cert", "tls.key": "key"}},
    ]}
    target: RequiredSecretsPresent = RequiredSecretsPresent(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is False


def test_required_secrets_missing_tls_key() -> None:
    """«wire-server-tls» secret missing the key file; should fail."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig-secrets"}, "data": {"zauth-key": "abc"}},
        {"metadata": {"name": "nginz-secrets"}, "data": {"zauth-pub": "def"}},
        {"metadata": {"name": "brig-turn"}, "data": {"turn-secret.txt": "ghi"}},
        {"metadata": {"name": "wire-server-tls"}, "data": {"tls.crt": "cert"}},
    ]}
    target: RequiredSecretsPresent = RequiredSecretsPresent(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is False


def test_required_secrets_null_data_raises() -> None:
    """Kubectl returns None instead of data; should raise RuntimeError."""
    target: RequiredSecretsPresent = RequiredSecretsPresent(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# MigrationJobsCompleted
# ---------------------------------------------------------------------------

def test_migration_jobs_description() -> None:
    """Should mention migrations in the description."""
    target: MigrationJobsCompleted = MigrationJobsCompleted(make_minimal_config(), _make_terminal(), _make_logger())
    assert "migration" in target.description.lower()


def test_migration_jobs_all_completed() -> None:
    """Both migrations ran to completion; should pass."""
    jobs_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "cassandra-migrations-abc"},
         "status": {"succeeded": 1, "failed": 0}},
        {"metadata": {"name": "brig-index-create-xyz"},
         "status": {"succeeded": 1, "failed": 0}},
    ]}
    target: MigrationJobsCompleted = MigrationJobsCompleted(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), jobs_data)):
        result: bool = target.collect()

    assert result is True


def test_migration_jobs_one_failed() -> None:
    """Galley migration failed three times; should fail."""
    jobs_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "cassandra-migrations-abc"},
         "status": {"succeeded": 1, "failed": 0}},
        {"metadata": {"name": "galley-migrate-xyz"},
         "status": {"succeeded": 0, "failed": 3}},
    ]}
    target: MigrationJobsCompleted = MigrationJobsCompleted(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), jobs_data)):
        result: bool = target.collect()

    assert result is False


def test_migration_jobs_none_found() -> None:
    """No migration jobs exist; nothing to check, so it's fine."""
    jobs_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "unrelated-job"}, "status": {"succeeded": 1}},
    ]}
    target: MigrationJobsCompleted = MigrationJobsCompleted(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), jobs_data)):
        result: bool = target.collect()

    assert result is True


def test_migration_jobs_null_data_raises() -> None:
    """Kubectl returns None instead of data; should raise RuntimeError."""
    target: MigrationJobsCompleted = MigrationJobsCompleted(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass
