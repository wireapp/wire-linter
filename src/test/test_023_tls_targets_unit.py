"""Tests for TLS targets.

Tests CertificateExpiration, KubeadmCertExpiration,
and OpensearchCertKeyUsage targets.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.tls.certificate_expiration import CertificateExpiration
from src.targets.tls.kubeadm_cert_expiration import KubeadmCertExpiration
from src.targets.tls.opensearch_cert_key_usage import OpensearchCertKeyUsage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terminal() -> Terminal:
    """Create a quiet terminal so we don't spam test output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Create a logger that suppresses everything."""
    return Logger(level=LogLevel.ERROR)


def _ssh_cmd_result(stdout: str) -> CommandResult:
    """Create a successful CommandResult for SSH output."""
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
    """Create a successful CommandResult for kubectl output."""
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
# CertificateExpiration
# ---------------------------------------------------------------------------

def test_certificate_expiration_description() -> None:
    """CertificateExpiration should mention expiration in its description."""
    target: CertificateExpiration = CertificateExpiration(make_minimal_config(), _make_terminal(), _make_logger())
    assert "expiration" in target.description.lower()


def test_certificate_expiration_unit() -> None:
    """CertificateExpiration should report its unit as « days »."""
    target: CertificateExpiration = CertificateExpiration(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == "days"


def test_certificate_expiration_parses_date() -> None:
    """CertificateExpiration should parse the openssl notAfter date."""
    # Date far in the future so the test doesn't break
    openssl_output: str = "notAfter=Dec 31 23:59:59 2099 GMT\n"
    target: CertificateExpiration = CertificateExpiration(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(openssl_output)):
        result: int = target.collect()

    # Way more than a year from now
    assert result > 365


def test_certificate_expiration_no_output_raises() -> None:
    """CertificateExpiration should raise if openssl can't get the cert."""
    target: CertificateExpiration = CertificateExpiration(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("connect: Connection refused\n")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# KubeadmCertExpiration
# ---------------------------------------------------------------------------

def test_kubeadm_cert_expiration_description() -> None:
    """KubeadmCertExpiration should mention kubeadm in its description."""
    target: KubeadmCertExpiration = KubeadmCertExpiration(make_minimal_config(), _make_terminal(), _make_logger())
    assert "kubeadm" in target.description.lower()


def _make_node_with_ip(ip: str) -> dict[str, Any]:
    """Create a Kubernetes node object with an InternalIP."""
    return {
        "metadata": {"name": "node-1"},
        "status": {"addresses": [{"type": "InternalIP", "address": ip}]},
    }


def test_kubeadm_cert_expiration_parses_days() -> None:
    """KubeadmCertExpiration should find the cert with the least time remaining."""
    kubeadm_output: str = (
        "CERTIFICATE                EXPIRES                  RESIDUAL TIME\n"
        "admin.conf                 Mar 15, 2027 12:00 UTC   364d\n"
        "apiserver                  Mar 15, 2027 12:00 UTC   364d\n"
        "etcd-server                Jun 01, 2026 12:00 UTC   77d\n"
    )
    nodes_data: dict[str, Any] = {"items": [_make_node_with_ip("10.0.0.5")]}
    target: KubeadmCertExpiration = KubeadmCertExpiration(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), nodes_data)):
        with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(kubeadm_output)):
            result: str = target.collect()

    # etcd-server has the least time; 77 days
    assert "77d" in result
    assert "etcd-server" in result


def test_kubeadm_cert_expiration_no_nodes_raises() -> None:
    """Raise if there are no nodes in the cluster."""
    nodes_data: dict[str, Any] = {"items": []}
    target: KubeadmCertExpiration = KubeadmCertExpiration(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), nodes_data)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# OpensearchCertKeyUsage
# ---------------------------------------------------------------------------

def test_opensearch_cert_key_usage_description() -> None:
    """OpensearchCertKeyUsage should mention opensearch in its description."""
    target: OpensearchCertKeyUsage = OpensearchCertKeyUsage(make_minimal_config(), _make_terminal(), _make_logger())
    assert "opensearch" in target.description.lower()


def test_opensearch_cert_key_usage_all_present() -> None:
    """Return True when the cert has all required key usages."""
    cert_text: str = (
        "X509v3 Key Usage:\n"
        "    Digital Signature, Key Encipherment\n"
        "X509v3 Extended Key Usage:\n"
        "    TLS Web Server Authentication\n"
    )
    target: OpensearchCertKeyUsage = OpensearchCertKeyUsage(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(cert_text)):
        result: bool = target.collect()

    assert result is True


def test_opensearch_cert_key_usage_missing_extension() -> None:
    """Return False if some key usages are missing."""
    cert_text: str = (
        "X509v3 Key Usage:\n"
        "    Digital Signature\n"
    )
    target: OpensearchCertKeyUsage = OpensearchCertKeyUsage(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(cert_text)):
        result: bool = target.collect()

    assert result is False


def test_opensearch_cert_key_usage_no_cert_raises() -> None:
    """Raise if we can't retrieve the certificate."""
    target: OpensearchCertKeyUsage = OpensearchCertKeyUsage(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass
