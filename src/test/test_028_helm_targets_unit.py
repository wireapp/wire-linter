"""Tests for Helm targets: listing releases and checking their deployment status.

Tests cover both SSH-based Helm targets (src/targets/helm/) and kubectl-based
direct targets (src/targets/direct/helm/) which query Kubernetes secrets
labeled «owner=helm» instead of running «helm list» over SSH.
"""

from __future__ import annotations

# External
import base64
import gzip
import json
from typing import Any
from unittest.mock import patch

# Ours
from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.helm.releases import HelmReleases
from src.targets.helm.release_status import HelmReleaseStatus
from src.targets.direct.helm.releases import HelmReleases as DirectHelmReleases
from src.targets.direct.helm.release_status import HelmReleaseStatus as DirectHelmReleaseStatus


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


# ---------------------------------------------------------------------------
# HelmReleases
# ---------------------------------------------------------------------------

def test_helm_releases_description() -> None:
    """Should mention Helm in the description."""
    target: HelmReleases = HelmReleases(make_minimal_config(), _make_terminal(), _make_logger())
    assert "helm" in target.description.lower()


def test_helm_releases_parses_json() -> None:
    """Parse JSON from «helm list»; should output release names and status."""
    helm_json: str = '[{"name":"wire-server","chart":"wire-server-4.50.0","status":"deployed"},{"name":"nginx","chart":"ingress-nginx-4.10.0","status":"deployed"}]'
    target: HelmReleases = HelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(helm_json)):
        result: str = target.collect()

    assert "wire-server" in result
    assert "nginx" in result
    assert "deployed" in result


def test_helm_releases_empty_raises() -> None:
    """No output from «helm list»; should raise RuntimeError."""
    target: HelmReleases = HelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_helm_releases_invalid_json_raises() -> None:
    """«helm list» output is garbage; should raise RuntimeError."""
    target: HelmReleases = HelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("not json")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# HelmReleaseStatus
# ---------------------------------------------------------------------------

def test_helm_release_status_description() -> None:
    """Should mention Helm."""
    target: HelmReleaseStatus = HelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())
    assert "helm" in target.description.lower()


def test_helm_release_status_all_deployed() -> None:
    """All releases show «deployed»; good."""
    helm_json: str = (
        '[{"name":"wire-server","namespace":"wire","revision":"5",'
        '"updated":"2026-03-14 12:00:00.123456 +0000 UTC","status":"deployed",'
        '"chart":"wire-server-4.50.0","app_version":"4.50.0"},'
        '{"name":"nginx","namespace":"ingress-nginx","revision":"3",'
        '"updated":"2026-03-14 12:00:00.123456 +0000 UTC","status":"deployed",'
        '"chart":"ingress-nginx-4.10.0","app_version":"1.10.0"}]'
    )
    target: HelmReleaseStatus = HelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(helm_json)):
        result: bool = target.collect()

    assert result is True


def test_helm_release_status_one_failed() -> None:
    """Nginx release is «failed»; should fail."""
    helm_json: str = (
        '[{"name":"wire-server","namespace":"wire","revision":"5",'
        '"updated":"2026-03-14 12:00:00.123456 +0000 UTC","status":"deployed",'
        '"chart":"wire-server-4.50.0","app_version":"4.50.0"},'
        '{"name":"nginx","namespace":"ingress-nginx","revision":"3",'
        '"updated":"2026-03-14 12:00:00.123456 +0000 UTC","status":"failed",'
        '"chart":"ingress-nginx-4.10.0","app_version":"1.10.0"}]'
    )
    target: HelmReleaseStatus = HelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(helm_json)):
        result: bool = target.collect()

    assert result is False


def test_helm_release_status_pending_install() -> None:
    """Release stuck on «pending-install»; should fail."""
    helm_json: str = (
        '[{"name":"wire-server","namespace":"wire","revision":"1",'
        '"updated":"2026-03-14 12:00:00.123456 +0000 UTC","status":"pending-install",'
        '"chart":"wire-server-4.50.0","app_version":"4.50.0"}]'
    )
    target: HelmReleaseStatus = HelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(helm_json)):
        result: bool = target.collect()

    assert result is False


def test_helm_release_status_empty_raises() -> None:
    """No output from «helm list»; should raise RuntimeError."""
    target: HelmReleaseStatus = HelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_helm_release_status_invalid_json_raises() -> None:
    """Invalid JSON from «helm list»; should raise RuntimeError."""
    target: HelmReleaseStatus = HelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("not json at all")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Direct (kubectl-based) Helm target helpers
# ---------------------------------------------------------------------------

def _kubectl_cmd_result(stdout: str = "{}") -> CommandResult:
    """Successful kubectl command result with given output."""
    return CommandResult(
        command="kubectl get secrets -o json",
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )


def _encode_helm_release(chart_name: str, chart_version: str, app_version: str = "") -> str:
    """Build a double-base64+gzip encoded Helm release payload.

    Mimics the encoding chain Helm uses for secret storage:
    K8s_base64( Helm_base64( gzip( json ) ) ).
    """
    # The release JSON that Helm stores inside the secret
    release_json: dict[str, Any] = {
        "chart": {
            "metadata": {
                "name": chart_name,
                "version": chart_version,
                "appVersion": app_version,
            }
        }
    }

    # Compress with gzip
    compressed: bytes = gzip.compress(json.dumps(release_json).encode())

    # Helm's base64 encoding
    helm_b64: bytes = base64.b64encode(compressed)

    # Kubernetes Secret base64 encoding (outer layer)
    k8s_b64: str = base64.b64encode(helm_b64).decode()

    return k8s_b64


def _make_helm_secret(
    release_name: str,
    namespace: str,
    revision: int,
    status: str,
    chart_name: str = "unknown",
    chart_version: str = "0.0.0",
    app_version: str = "",
    creation_timestamp: str = "2026-03-14T12:00:00Z",
) -> dict[str, Any]:
    """Build a Kubernetes Secret dict mimicking a Helm release secret.

    The secret name follows «sh.helm.release.v1.<name>.v<revision>» and
    labels include «owner=helm», «name=<release>», «status=<status>».
    """
    return {
        "metadata": {
            "name": f"sh.helm.release.v1.{release_name}.v{revision}",
            "namespace": namespace,
            "creationTimestamp": creation_timestamp,
            "labels": {
                "owner": "helm",
                "name": release_name,
                "status": status,
            },
        },
        "data": {
            "release": _encode_helm_release(chart_name, chart_version, app_version),
        },
    }


def _kubectl_secrets_response(items: list[dict[str, Any]]) -> tuple[CommandResult, dict[str, Any]]:
    """Build the (CommandResult, parsed_json) tuple that run_kubectl returns."""
    parsed: dict[str, Any] = {"items": items}
    stdout: str = json.dumps(parsed)
    return _kubectl_cmd_result(stdout), parsed


# ---------------------------------------------------------------------------
# Direct HelmReleases (kubectl-based)
# ---------------------------------------------------------------------------

def test_direct_helm_releases_description() -> None:
    """Should mention Helm in the description."""
    target: DirectHelmReleases = DirectHelmReleases(make_minimal_config(), _make_terminal(), _make_logger())
    assert "helm" in target.description.lower()


def test_direct_helm_releases_lists_releases() -> None:
    """Parse kubectl secrets; should output release names, chart versions, and status."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 5, "deployed", "wire-server", "4.50.0", "4.50.0"),
        _make_helm_secret("nginx", "ingress-nginx", 3, "deployed", "ingress-nginx", "4.10.0", "1.10.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleases = DirectHelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: str = target.collect()

    # Should contain both release names with their chart versions
    assert "wire-server" in result
    assert "nginx" in result
    assert "deployed" in result


def test_direct_helm_releases_picks_latest_revision() -> None:
    """When multiple revisions exist for a release, only the latest is reported."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 1, "deployed", "wire-server", "4.48.0"),
        _make_helm_secret("wire-server", "wire", 3, "deployed", "wire-server", "4.50.0"),
        _make_helm_secret("wire-server", "wire", 2, "deployed", "wire-server", "4.49.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleases = DirectHelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: str = target.collect()

    # Latest revision (v3) has chart version 4.50.0
    assert "4.50.0" in result

    # Older revisions should not appear
    assert "4.48.0" not in result
    assert "4.49.0" not in result


def test_direct_helm_releases_no_secrets_raises() -> None:
    """No Helm release secrets found; should raise RuntimeError."""
    cmd_result, parsed = _kubectl_secrets_response([])
    target: DirectHelmReleases = DirectHelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_direct_helm_releases_null_data_raises() -> None:
    """kubectl returns None for parsed data; should raise RuntimeError."""
    cmd_result: CommandResult = _kubectl_cmd_result("")
    target: DirectHelmReleases = DirectHelmReleases(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Direct HelmReleaseStatus (kubectl-based)
# ---------------------------------------------------------------------------

def test_direct_helm_release_status_description() -> None:
    """Should mention Helm in the description."""
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())
    assert "helm" in target.description.lower()


def test_direct_helm_release_status_all_deployed() -> None:
    """All releases in «deployed» state; should return True."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 5, "deployed", "wire-server", "4.50.0", "4.50.0"),
        _make_helm_secret("nginx", "ingress-nginx", 3, "deployed", "ingress-nginx", "4.10.0", "1.10.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: bool = target.collect()

    assert result is True


def test_direct_helm_release_status_one_failed() -> None:
    """One release is «failed»; should return False."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 5, "deployed", "wire-server", "4.50.0", "4.50.0"),
        _make_helm_secret("nginx", "ingress-nginx", 3, "failed", "ingress-nginx", "4.10.0", "1.10.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: bool = target.collect()

    assert result is False


def test_direct_helm_release_status_pending_install() -> None:
    """Release stuck on «pending-install»; should return False."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 1, "pending-install", "wire-server", "4.50.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: bool = target.collect()

    assert result is False


def test_direct_helm_release_status_pending_upgrade() -> None:
    """Release stuck on «pending-upgrade»; should return False."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 3, "pending-upgrade", "wire-server", "4.50.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: bool = target.collect()

    assert result is False


def test_direct_helm_release_status_picks_latest_revision() -> None:
    """Only the latest revision per release determines its status."""
    items: list[dict[str, Any]] = [
        # Older revision was failed, but latest is deployed — should pass
        _make_helm_secret("wire-server", "wire", 1, "failed", "wire-server", "4.48.0"),
        _make_helm_secret("wire-server", "wire", 3, "deployed", "wire-server", "4.50.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        result: bool = target.collect()

    assert result is True


def test_direct_helm_release_status_no_secrets_raises() -> None:
    """No Helm release secrets found; should raise RuntimeError."""
    cmd_result, parsed = _kubectl_secrets_response([])
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_direct_helm_release_status_null_data_raises() -> None:
    """kubectl returns None for parsed data; should raise RuntimeError."""
    cmd_result: CommandResult = _kubectl_cmd_result("")
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_direct_helm_release_status_tabular_output() -> None:
    """The raw output should contain tabular format for UI version parsing."""
    items: list[dict[str, Any]] = [
        _make_helm_secret("wire-server", "wire", 5, "deployed", "wire-server", "4.50.0", "4.50.0"),
    ]
    cmd_result, parsed = _kubectl_secrets_response(items)
    target: DirectHelmReleaseStatus = DirectHelmReleaseStatus(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(cmd_result, parsed)):
        target.collect()

    # The raw output should contain the tabular header and chart version for UI parsing
    raw: str = "\n".join(target._raw_outputs)
    assert "wire-server-4.50.0" in raw
    assert "NAME" in raw
