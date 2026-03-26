"""Tests for security checks: internal endpoints, RabbitMQ credentials, and Stern exposure.

These targets verify that services aren't accidentally exposed to the public, that
RabbitMQ isn't running with default credentials, and that Stern (backoffice) isn't
accessible from the internet.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.security.internal_endpoints_blocked import InternalEndpointsBlocked
from src.targets.security.rabbitmq_default_credentials import RabbitmqDefaultCredentials
from src.targets.security.stern_not_exposed import SternNotExposed


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


def _b64(value: str) -> str:
    """Quick base64 encode for fake Kubernetes secret data."""
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# InternalEndpointsBlocked
# ---------------------------------------------------------------------------

def test_internal_endpoints_blocked_description() -> None:
    """Should have a description that mentions internal endpoints."""
    target: InternalEndpointsBlocked = InternalEndpointsBlocked(make_minimal_config(), _make_terminal(), _make_logger())
    assert "/i/" in target.description


def test_internal_endpoints_blocked_all_blocked() -> None:
    """All endpoints return 403; should pass the check."""
    target: InternalEndpointsBlocked = InternalEndpointsBlocked(make_minimal_config(), _make_terminal(), _make_logger())

    # Everything returns 403, so they're blocked from public access
    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("403")):
        result: bool = target.collect()

    assert result is True


def test_internal_endpoints_blocked_one_accessible() -> None:
    """One endpoint returns 200; should fail the check."""
    target: InternalEndpointsBlocked = InternalEndpointsBlocked(make_minimal_config(), _make_terminal(), _make_logger())

    # First one is exposed (200), rest blocked (404) — one leak is enough to fail
    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result("200"),
    ] + [_ssh_cmd_result("404")] * 7):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# RabbitmqDefaultCredentials
# ---------------------------------------------------------------------------

def test_rabbitmq_default_credentials_description() -> None:
    """Should mention RabbitMQ in the description."""
    target: RabbitmqDefaultCredentials = RabbitmqDefaultCredentials(make_minimal_config(), _make_terminal(), _make_logger())
    assert "rabbitmq" in target.description.lower()


def test_rabbitmq_default_credentials_safe() -> None:
    """Custom credentials like «wire-admin»; should pass."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "rabbitmq-credentials"},
         "data": {"username": _b64("wire-admin"), "password": _b64("supersecret")}},
    ]}
    target: RabbitmqDefaultCredentials = RabbitmqDefaultCredentials(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is True


def test_rabbitmq_default_credentials_unsafe() -> None:
    """Default «guest/guest» credentials; should fail."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "rabbitmq-credentials"},
         "data": {"username": _b64("guest"), "password": _b64("guest")}},
    ]}
    target: RabbitmqDefaultCredentials = RabbitmqDefaultCredentials(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is False


def test_rabbitmq_default_credentials_no_secret() -> None:
    """No RabbitMQ secret at all; fine, can't check defaults that don't exist."""
    secrets_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig-secrets"}, "data": {"key": _b64("value")}},
    ]}
    target: RabbitmqDefaultCredentials = RabbitmqDefaultCredentials(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), secrets_data)):
        result: bool = target.collect()

    assert result is True


# ---------------------------------------------------------------------------
# SternNotExposed
# ---------------------------------------------------------------------------

def test_stern_not_exposed_description() -> None:
    """Should mention Stern or backoffice in the description."""
    target: SternNotExposed = SternNotExposed(make_minimal_config(), _make_terminal(), _make_logger())
    assert "stern" in target.description.lower() or "backoffice" in target.description.lower()


def test_stern_not_exposed_safe() -> None:
    """No ingress routes to Stern; should pass."""
    ingress_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "webapp-ingress", "namespace": "wire"},
         "spec": {"rules": [
             {"http": {"paths": [
                 {"backend": {"service": {"name": "webapp"}}},
             ]}},
         ]}},
    ]}
    target: SternNotExposed = SternNotExposed(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), ingress_data)):
        result: bool = target.collect()

    assert result is True


def test_stern_not_exposed_ingress_name_match() -> None:
    """Ingress named «stern-ingress»; should fail."""
    ingress_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "stern-ingress", "namespace": "wire"},
         "spec": {"rules": []}},
    ]}
    target: SternNotExposed = SternNotExposed(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), ingress_data)):
        result: bool = target.collect()

    assert result is False


def test_stern_not_exposed_backend_match() -> None:
    """Ingress routes to the «stern» service; should fail."""
    ingress_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "admin-ingress", "namespace": "wire"},
         "spec": {"rules": [
             {"http": {"paths": [
                 {"backend": {"service": {"name": "stern"}}},
             ]}},
         ]}},
    ]}
    target: SternNotExposed = SternNotExposed(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), ingress_data)):
        result: bool = target.collect()

    assert result is False
