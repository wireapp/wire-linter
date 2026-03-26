"""Tests for config targets.

Tests all the config validation targets: BrigFederationDomain, CertmanagerTestMode,
DatabaseHostConsistency, DeeplinkJson, EphemeralInProduction, FederationDomain,
GalleyFeatureFlags, IngressProxyProtocol, IsSelfHosted, and WebappBackendUrls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.config.brig_federation_domain import BrigFederationDomain
from src.targets.config.certmanager_test_mode import CertmanagerTestMode
from src.targets.config.database_host_consistency import DatabaseHostConsistency
from src.targets.config.deeplink_json import DeeplinkJson
from src.targets.config.ephemeral_in_production import EphemeralInProduction
from src.targets.config.federation_domain import FederationDomain
from src.targets.config.galley_feature_flags import GalleyFeatureFlags
from src.targets.config.ingress_proxy_protocol import IngressProxyProtocol
from src.targets.config.is_self_hosted import IsSelfHosted
from src.targets.config.webapp_backend_urls import WebappBackendUrls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terminal() -> Terminal:
    """Create a quiet terminal so we don't spam test output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Create a logger that suppresses everything."""
    return Logger(level=LogLevel.ERROR)


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
# BrigFederationDomain
# ---------------------------------------------------------------------------

def test_brig_federation_domain_description() -> None:
    """BrigFederationDomain should have a description about federation domain."""
    target: BrigFederationDomain = BrigFederationDomain(make_minimal_config(), _make_terminal(), _make_logger())
    assert "federation domain" in target.description.lower()


def test_brig_federation_domain_match() -> None:
    """Return True when the brig domain matches the cluster domain."""
    brig_cm: dict[str, Any] = {
        "data": {"brig.yaml": "optSettings:\n  setFederationDomain: example.com\n"},
    }
    target: BrigFederationDomain = BrigFederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), brig_cm)):
        result: bool = target.collect()

    assert result is True


def test_brig_federation_domain_mismatch() -> None:
    """Return False when the domains don't match."""
    brig_cm: dict[str, Any] = {
        "data": {"brig.yaml": "optSettings:\n  setFederationDomain: wrong.example.org\n"},
    }
    target: BrigFederationDomain = BrigFederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), brig_cm)):
        result: bool = target.collect()

    assert result is False


def test_brig_federation_domain_not_set() -> None:
    """If the domain isn't set, return False (missing federation domain is unhealthy)."""
    brig_cm: dict[str, Any] = {
        "data": {"brig.yaml": "optSettings:\n  setFoo: bar\n"},
    }
    target: BrigFederationDomain = BrigFederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), brig_cm)):
        result: bool = target.collect()

    assert result is False


def test_brig_federation_domain_no_configmap_raises() -> None:
    """Raise if we can't get the brig ConfigMap."""
    target: BrigFederationDomain = BrigFederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# CertmanagerTestMode
# ---------------------------------------------------------------------------

def test_certmanager_test_mode_description() -> None:
    """CertmanagerTestMode should mention cert-manager in its description."""
    target: CertmanagerTestMode = CertmanagerTestMode(make_minimal_config(), _make_terminal(), _make_logger())
    assert "cert-manager" in target.description.lower()


def test_certmanager_test_mode_production() -> None:
    """Return True when all issuers are pointing to production ACME."""
    issuer_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "letsencrypt-prod"},
         "spec": {"acme": {"server": "https://acme-v02.api.letsencrypt.org/directory"}}},
    ]}
    ingress_data: dict[str, Any] = {"items": []}
    target: CertmanagerTestMode = CertmanagerTestMode(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), issuer_data),
        (_kubectl_cmd_result(), ingress_data),
    ]):
        result: bool = target.collect()

    assert result is True


def test_certmanager_test_mode_staging() -> None:
    """Return False if any issuer is using the staging ACME endpoint."""
    issuer_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "letsencrypt-staging"},
         "spec": {"acme": {"server": "https://acme-staging-v02.api.letsencrypt.org/directory"}}},
    ]}
    ingress_data: dict[str, Any] = {"items": []}
    target: CertmanagerTestMode = CertmanagerTestMode(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), issuer_data),
        (_kubectl_cmd_result(), ingress_data),
    ]):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# DatabaseHostConsistency
# ---------------------------------------------------------------------------

def test_database_host_consistency_description() -> None:
    """DatabaseHostConsistency should mention consistency in its description."""
    target: DatabaseHostConsistency = DatabaseHostConsistency(make_minimal_config(), _make_terminal(), _make_logger())
    assert "consistency" in target.description.lower()


def test_database_host_consistency_consistent() -> None:
    """Return True when all services are pointing to the same database host."""
    brig_cm: dict[str, Any] = {"data": {"brig.yaml": "cassandra:\n  host: 10.0.0.10\n"}}
    galley_cm: dict[str, Any] = {"data": {"galley.yaml": "cassandra:\n  host: 10.0.0.10\n"}}
    # Services that don't have a configmap
    empty_cm: dict[str, Any] = {}

    target: DatabaseHostConsistency = DatabaseHostConsistency(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), brig_cm),
        (_kubectl_cmd_result(), galley_cm),
        (_kubectl_cmd_result(), empty_cm),
        (_kubectl_cmd_result(), empty_cm),
        (_kubectl_cmd_result(), empty_cm),
    ]):
        result: bool = target.collect()

    assert result is True


def test_database_host_consistency_inconsistent() -> None:
    """Return False if services are pointing to different database hosts."""
    brig_cm: dict[str, Any] = {"data": {"brig.yaml": "cassandra:\n  host: 10.0.0.10\n"}}
    galley_cm: dict[str, Any] = {"data": {"galley.yaml": "cassandra:\n  host: 10.0.0.99\n"}}
    empty_cm: dict[str, Any] = {}

    target: DatabaseHostConsistency = DatabaseHostConsistency(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), brig_cm),
        (_kubectl_cmd_result(), galley_cm),
        (_kubectl_cmd_result(), empty_cm),
        (_kubectl_cmd_result(), empty_cm),
        (_kubectl_cmd_result(), empty_cm),
    ]):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# DeeplinkJson
# ---------------------------------------------------------------------------

def test_deeplink_json_description() -> None:
    """DeeplinkJson should mention deeplink in its description."""
    target: DeeplinkJson = DeeplinkJson(make_minimal_config(), _make_terminal(), _make_logger())
    assert "deeplink" in target.description.lower()


def test_deeplink_json_all_keys_present() -> None:
    """Return True when deeplink.json has all the required keys."""
    json_response: str = '{"backendURL":"https://a","backendWSURL":"wss://a","teamsURL":"https://t","accountsURL":"https://ac","blackListURL":"https://bl","websiteURL":"https://w","title":"Wire"}'
    target: DeeplinkJson = DeeplinkJson(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(json_response)):
        result: bool = target.collect()

    assert result is True


def test_deeplink_json_missing_keys() -> None:
    """Return False if some required keys are missing from deeplink.json."""
    json_response: str = '{"backendURL":"https://a","title":"Wire"}'
    target: DeeplinkJson = DeeplinkJson(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(json_response)):
        result: bool = target.collect()

    assert result is False


def test_deeplink_json_empty_response_raises() -> None:
    """Raise if we can't fetch deeplink.json at all."""
    target: DeeplinkJson = DeeplinkJson(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# EphemeralInProduction
# ---------------------------------------------------------------------------

def test_ephemeral_in_production_description() -> None:
    """EphemeralInProduction should mention ephemeral in its description."""
    target: EphemeralInProduction = EphemeralInProduction(make_minimal_config(), _make_terminal(), _make_logger())
    assert "ephemeral" in target.description.lower()


def test_ephemeral_in_production_clean() -> None:
    """Return « production » when there are no ephemeral deployments."""
    deploy_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig", "namespace": "wire"}},
    ]}
    ss_data: dict[str, Any] = {"items": []}
    target: EphemeralInProduction = EphemeralInProduction(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), deploy_data),
        (_kubectl_cmd_result(), ss_data),
    ]):
        result: str = target.collect()

    assert result == "production"


def test_ephemeral_in_production_found() -> None:
    """Return « ephemeral » when ephemeral deployments are found."""
    deploy_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "databases-ephemeral", "namespace": "wire"}},
    ]}
    ss_data: dict[str, Any] = {"items": []}
    target: EphemeralInProduction = EphemeralInProduction(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), deploy_data),
        (_kubectl_cmd_result(), ss_data),
    ]):
        result: str = target.collect()

    assert result == "ephemeral"


# ---------------------------------------------------------------------------
# FederationDomain
# ---------------------------------------------------------------------------

def test_federation_domain_description() -> None:
    """FederationDomain should mention federation in its description."""
    target: FederationDomain = FederationDomain(make_minimal_config(), _make_terminal(), _make_logger())
    assert "federation" in target.description.lower()


def test_federation_domain_consistent() -> None:
    """Return True when brig and galley have the same federation domain."""
    brig_cm: dict[str, Any] = {"data": {"brig.yaml": "optSettings:\n  setFederationDomain: example.com\n"}}
    galley_cm: dict[str, Any] = {"data": {"galley.yaml": "settings:\n  federationDomain: example.com\n"}}
    target: FederationDomain = FederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), brig_cm),
        (_kubectl_cmd_result(), galley_cm),
    ]):
        result: bool = target.collect()

    assert result is True


def test_federation_domain_mismatch() -> None:
    """Return False when the two services have different domains."""
    brig_cm: dict[str, Any] = {"data": {"brig.yaml": "optSettings:\n  setFederationDomain: wire.example.com\n"}}
    galley_cm: dict[str, Any] = {"data": {"galley.yaml": "settings:\n  federationDomain: other.example.com\n"}}
    target: FederationDomain = FederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), brig_cm),
        (_kubectl_cmd_result(), galley_cm),
    ]):
        result: bool = target.collect()

    assert result is False


def test_federation_domain_both_missing() -> None:
    """Return 'not_configured' when neither service has a federation domain set."""
    brig_cm: dict[str, Any] = {"data": {"brig.yaml": "optSettings:\n  setFoo: bar\n"}}
    galley_cm: dict[str, Any] = {"data": {"galley.yaml": "settings:\n  foo: bar\n"}}
    target: FederationDomain = FederationDomain(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), brig_cm),
        (_kubectl_cmd_result(), galley_cm),
    ]):
        result: bool | str = target.collect()

    assert result == "not_configured"


# ---------------------------------------------------------------------------
# GalleyFeatureFlags
# ---------------------------------------------------------------------------

def test_galley_feature_flags_description() -> None:
    """GalleyFeatureFlags should mention feature flag in its description."""
    target: GalleyFeatureFlags = GalleyFeatureFlags(make_minimal_config(), _make_terminal(), _make_logger())
    assert "feature flag" in target.description.lower()


def test_galley_feature_flags_all_present() -> None:
    """Return True when all required feature flags are defined."""
    galley_yaml: str = (
        "settings:\n"
        "  featureFlags:\n"
        "    sso: enabled-by-default\n"
        "    legalhold: disabled-by-default\n"
        "    teamSearchVisibility: enabled\n"
        "    mls: enabled\n"
        "    mlsMigration: disabled\n"
    )
    cm: dict[str, Any] = {"data": {"galley.yaml": galley_yaml}}
    target: GalleyFeatureFlags = GalleyFeatureFlags(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: bool = target.collect()

    assert result is True


def test_galley_feature_flags_missing_some() -> None:
    """Return False if some required flags are missing."""
    galley_yaml: str = (
        "settings:\n"
        "  featureFlags:\n"
        "    sso: enabled\n"
    )
    cm: dict[str, Any] = {"data": {"galley.yaml": galley_yaml}}
    target: GalleyFeatureFlags = GalleyFeatureFlags(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# IngressProxyProtocol
# ---------------------------------------------------------------------------

def test_ingress_proxy_protocol_description() -> None:
    """IngressProxyProtocol should mention proxy protocol in its description."""
    target: IngressProxyProtocol = IngressProxyProtocol(make_minimal_config(), _make_terminal(), _make_logger())
    assert "proxy protocol" in target.description.lower()


def test_ingress_proxy_protocol_enabled() -> None:
    """Return « enabled » when use-proxy-protocol is true."""
    cm: dict[str, Any] = {"kind": "ConfigMap", "data": {"use-proxy-protocol": "true"}}
    target: IngressProxyProtocol = IngressProxyProtocol(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: str = target.collect()

    assert result == "enabled"


def test_ingress_proxy_protocol_disabled() -> None:
    """Return « disabled » when use-proxy-protocol is false."""
    cm: dict[str, Any] = {"kind": "ConfigMap", "data": {"use-proxy-protocol": "false"}}
    target: IngressProxyProtocol = IngressProxyProtocol(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: str = target.collect()

    assert result == "disabled"


def test_ingress_proxy_protocol_not_found() -> None:
    """Return « not_found » if the ingress configmap doesn't exist."""
    target: IngressProxyProtocol = IngressProxyProtocol(make_minimal_config(), _make_terminal(), _make_logger())

    # All namespace/name combinations return non-ConfigMap data
    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        result: str = target.collect()

    assert result == "not_found"


# ---------------------------------------------------------------------------
# IsSelfHosted
# ---------------------------------------------------------------------------

def test_is_self_hosted_description() -> None:
    """IsSelfHosted should mention IS_SELF_HOSTED in its description."""
    target: IsSelfHosted = IsSelfHosted(make_minimal_config(), _make_terminal(), _make_logger())
    assert "IS_SELF_HOSTED" in target.description


def test_is_self_hosted_both_set() -> None:
    """Return True when both services have IS_SELF_HOSTED set to true."""
    def _deploy_with_env(value: str) -> dict[str, Any]:
        return {"spec": {"template": {"spec": {"containers": [
            {"name": "main", "env": [{"name": "IS_SELF_HOSTED", "value": value}]},
        ]}}}}

    target: IsSelfHosted = IsSelfHosted(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), _deploy_with_env("true")),
        (_kubectl_cmd_result(), _deploy_with_env("true")),
    ]):
        result: bool = target.collect()

    assert result is True


def test_is_self_hosted_one_missing() -> None:
    """Return False if one service doesn't have IS_SELF_HOSTED."""
    deploy_with: dict[str, Any] = {"spec": {"template": {"spec": {"containers": [
        {"name": "main", "env": [{"name": "IS_SELF_HOSTED", "value": "true"}]},
    ]}}}}
    deploy_without: dict[str, Any] = {"spec": {"template": {"spec": {"containers": [
        {"name": "main", "env": []},
    ]}}}}

    target: IsSelfHosted = IsSelfHosted(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), deploy_with),
        (_kubectl_cmd_result(), deploy_without),
    ]):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# WebappBackendUrls
# ---------------------------------------------------------------------------

def test_webapp_backend_urls_description() -> None:
    """WebappBackendUrls should mention placeholder in its description."""
    target: WebappBackendUrls = WebappBackendUrls(make_minimal_config(), _make_terminal(), _make_logger())
    assert "placeholder" in target.description.lower()


def test_webapp_backend_urls_no_placeholders() -> None:
    """Return "ok" when there are no placeholder URLs."""
    cm: dict[str, Any] = {"data": {"config.json": '{"backendURL": "https://wire.production.com"}'}}
    target: WebappBackendUrls = WebappBackendUrls(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: str | None = target.collect()

    assert result == "ok"


def test_webapp_backend_urls_has_placeholders() -> None:
    """Return "error" if definite placeholder URLs are still in the config."""
    cm: dict[str, Any] = {"data": {"config.json": 'backendURL=https://example.com/api'}}
    target: WebappBackendUrls = WebappBackendUrls(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: str | None = target.collect()

    assert result == "error"


def test_webapp_backend_urls_localhost_is_warning() -> None:
    """Return "warning" when only localhost/127.0.0.1 URLs are found."""
    cm: dict[str, Any] = {"data": {"config.json": 'backendURL=http://localhost:8080/api'}}
    target: WebappBackendUrls = WebappBackendUrls(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: str | None = target.collect()

    assert result == "warning"


def test_webapp_backend_urls_error_takes_precedence_over_warning() -> None:
    """Return "error" when both error and warning patterns are present."""
    cm: dict[str, Any] = {"data": {"config.json": 'backendURL=https://example.com\nredis=http://localhost:6379'}}
    target: WebappBackendUrls = WebappBackendUrls(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), cm)):
        result: str | None = target.collect()

    assert result == "error"
