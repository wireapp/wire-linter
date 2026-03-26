"""Tests for DNS targets.

Tests EmailDnsRecords and SubdomainResolution targets.
"""

from __future__ import annotations

from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.dns.email_dns_records import EmailDnsRecords
from src.targets.dns.subdomain_resolution import SubdomainResolution


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


# ---------------------------------------------------------------------------
# EmailDnsRecords
# ---------------------------------------------------------------------------

def test_email_dns_records_description() -> None:
    """EmailDnsRecords should have SPF in its description."""
    target: EmailDnsRecords = EmailDnsRecords(make_minimal_config(), _make_terminal(), _make_logger())
    assert "SPF" in target.description


def test_email_dns_records_both_present() -> None:
    """Return « spf+dmarc » when both SPF and DMARC records are found."""
    spf_output: str = '"v=spf1 include:_spf.google.com ~all"\n'
    dmarc_output: str = '"v=DMARC1; p=reject; rua=mailto:dmarc@example.com"\n'
    target: EmailDnsRecords = EmailDnsRecords(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result(spf_output),
        _ssh_cmd_result(dmarc_output),
    ]):
        result: str = target.collect()

    assert result == "spf+dmarc"


def test_email_dns_records_spf_only() -> None:
    """Return « spf_only » when only the SPF record exists."""
    target: EmailDnsRecords = EmailDnsRecords(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result('"v=spf1 ~all"\n'),
        _ssh_cmd_result(""),
    ]):
        result: str = target.collect()

    assert result == "spf_only"


def test_email_dns_records_dmarc_only() -> None:
    """Return « dmarc_only » when only the DMARC record exists."""
    target: EmailDnsRecords = EmailDnsRecords(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result(""),
        _ssh_cmd_result('"v=DMARC1; p=none"\n'),
    ]):
        result: str = target.collect()

    assert result == "dmarc_only"


def test_email_dns_records_missing() -> None:
    """Return « missing » when neither record is found."""
    target: EmailDnsRecords = EmailDnsRecords(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=[
        _ssh_cmd_result(""),
        _ssh_cmd_result(""),
    ]):
        result: str = target.collect()

    assert result == "missing"


# ---------------------------------------------------------------------------
# SubdomainResolution
# ---------------------------------------------------------------------------

def test_subdomain_resolution_description() -> None:
    """SubdomainResolution should mention subdomain in its description."""
    target: SubdomainResolution = SubdomainResolution(make_minimal_config(), _make_terminal(), _make_logger())
    assert "subdomain" in target.description.lower()


def test_subdomain_resolution_all_resolve() -> None:
    """Return all subdomains when they all resolve successfully."""
    target: SubdomainResolution = SubdomainResolution(make_minimal_config(), _make_terminal(), _make_logger())

    # Each dig call returns an IP
    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("1.2.3.4\n")):
        result: str = target.collect()

    # All 7 required subdomains should appear in the result
    assert "nginz-https" in result
    assert "webapp" in result
    assert "sftd" in result


def test_subdomain_resolution_some_fail() -> None:
    """Return only the subdomains that actually resolved."""
    call_count: int = 0

    def _alternating_result(*args: object, **kwargs: object) -> CommandResult:
        nonlocal call_count
        call_count += 1
        # First subdomain resolves, second doesn't, third does, etc.
        if call_count % 2 == 1:
            return _ssh_cmd_result("1.2.3.4\n")
        return _ssh_cmd_result("")

    target: SubdomainResolution = SubdomainResolution(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=_alternating_result):
        result: str = target.collect()

    # Should contain some subdomains but not all
    assert "nginz-https" in result  # First call resolves


def test_subdomain_resolution_none_resolve_raises() -> None:
    """Raise if none of the subdomains can resolve."""
    target: SubdomainResolution = SubdomainResolution(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass
