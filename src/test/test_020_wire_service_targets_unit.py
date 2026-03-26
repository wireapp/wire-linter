"""Tests for Wire service targets.

Tests all 13 healthy.py targets, 7 replicas.py targets, and other service targets.
We mock get_service_pods to control what each target's collect() method sees.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.command import CommandResult
from src.lib.config import Config
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.wire_services.brig.healthy import BrigHealthy
from src.targets.wire_services.brig.replicas import BrigReplicas
from src.targets.wire_services.galley.healthy import GalleyHealthy
from src.targets.wire_services.galley.replicas import GalleyReplicas
from src.targets.wire_services.cannon.healthy import CannonHealthy
from src.targets.wire_services.cannon.replicas import CannonReplicas
from src.targets.wire_services.cargohold.healthy import CargoholdHealthy
from src.targets.wire_services.cargohold.replicas import CargoholdReplicas
from src.targets.wire_services.gundeck.healthy import GundeckHealthy
from src.targets.wire_services.gundeck.replicas import GundeckReplicas
from src.targets.wire_services.spar.healthy import SparHealthy
from src.targets.wire_services.spar.replicas import SparReplicas
from src.targets.wire_services.nginz.healthy import NginzHealthy
from src.targets.wire_services.nginz.replicas import NginzReplicas
from src.targets.wire_services.background_worker.healthy import BackgroundWorkerHealthy
from src.targets.wire_services.sftd.healthy import SftdHealthy
from src.targets.wire_services.coturn.healthy import CoturnHealthy
from src.targets.wire_services.webapp.healthy import WebappHealthy
from src.targets.wire_services.team_settings.healthy import TeamSettingsHealthy
from src.targets.wire_services.account_pages.healthy import AccountPagesHealthy
from src.targets.wire_services.asset_host import AssetHost
from src.targets.wire_services.ingress_response import IngressResponse
from src.targets.wire_services.service_list import ServiceList
from src.targets.wire_services.status_endpoints import StatusEndpoints
from src.targets.wire_services.webapp_http import WebappHttp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> Config:
    """Create a minimal valid Config.

    Just delegates to make_minimal_config() so we don't duplicate the logic
    if it ever changes.
    """
    return make_minimal_config()


def _make_terminal() -> Terminal:
    """Create a quiet terminal so we don't spam test output."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Create a logger that suppresses everything."""
    return Logger(level=LogLevel.ERROR)


def _cmd_result(stdout: str = "", command: str = "kubectl") -> CommandResult:
    """Construct a successful CommandResult with the given stdout."""
    return CommandResult(
        command=command,
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.01,
        success=True,
        timed_out=False,
    )


def _make_pod(name: str, phase: str = "Running", ready: bool = True) -> dict[str, Any]:
    """Create a minimal pod dict that looks like kubectl JSON output."""
    return {
        "metadata": {"name": name},
        "status": {
            "phase": phase,
            "containerStatuses": [{"ready": ready}],
        },
    }


def _healthy_pods(service_name: str, count: int = 3) -> tuple[CommandResult, list[dict[str, Any]]]:
    """Create a (CommandResult, pods) tuple with N healthy pods ready to go."""
    pods: list[dict[str, Any]] = [
        _make_pod(f"{service_name}-{i}", phase="Running", ready=True)
        for i in range(count)
    ]
    return (_cmd_result(), pods)


def _unhealthy_pods(service_name: str) -> tuple[CommandResult, list[dict[str, Any]]]:
    """Create a (CommandResult, pods) tuple with one unhealthy pod mixed in."""
    pods: list[dict[str, Any]] = [
        _make_pod(f"{service_name}-0", phase="Running", ready=True),
        _make_pod(f"{service_name}-1", phase="Pending", ready=False),
    ]
    return (_cmd_result(), pods)


def _no_pods() -> tuple[CommandResult, list[dict[str, Any]]]:
    """Create an empty pods response."""
    return (_cmd_result(), [])


# ===========================================================================
# Brig: healthy and replicas
# ===========================================================================

def test_brig_healthy_description() -> None:
    """BrigHealthy should have a reasonable description."""
    target: BrigHealthy = BrigHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Brig (user accounts) - all replicas running"


def test_brig_healthy_returns_true() -> None:
    """When all pods are healthy, BrigHealthy returns True."""
    target: BrigHealthy = BrigHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.brig.healthy.get_service_pods", return_value=_healthy_pods("brig")):
        result: bool = target.collect()

    assert result is True


def test_brig_healthy_sets_dynamic_description() -> None:
    """BrigHealthy should update its description to show the replica count."""
    target: BrigHealthy = BrigHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.brig.healthy.get_service_pods", return_value=_healthy_pods("brig", 3)):
        target.collect()

    assert target._dynamic_description == "Brig (user accounts) - 3 replicas running"


def test_brig_healthy_returns_false() -> None:
    """Unhealthy pods should make BrigHealthy return False."""
    target: BrigHealthy = BrigHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.brig.healthy.get_service_pods", return_value=_unhealthy_pods("brig")):
        result: bool = target.collect()

    assert result is False


def test_brig_healthy_no_pods() -> None:
    """No pods at all? BrigHealthy should return False."""
    target: BrigHealthy = BrigHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.brig.healthy.get_service_pods", return_value=_no_pods()):
        result: bool = target.collect()

    assert result is False


def test_brig_replicas_description() -> None:
    """BrigReplicas should have a description about the replica count."""
    target: BrigReplicas = BrigReplicas(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Number of Brig pod replicas"


def test_brig_replicas_unit() -> None:
    """BrigReplicas should report its unit as « pods »."""
    target: BrigReplicas = BrigReplicas(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "pods"


def test_brig_replicas_count() -> None:
    """BrigReplicas should return the right count of running pods."""
    target: BrigReplicas = BrigReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.brig.replicas.get_service_pods", return_value=_healthy_pods("brig", 3)):
        result: int = target.collect()

    assert result == 3


# ===========================================================================
# Galley: healthy and replicas
# ===========================================================================

def test_galley_healthy_description() -> None:
    """GalleyHealthy should have a reasonable description."""
    target: GalleyHealthy = GalleyHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Galley (conversations) - all replicas running"


def test_galley_healthy_returns_true() -> None:
    """Healthy pods mean GalleyHealthy returns True."""
    target: GalleyHealthy = GalleyHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.galley.healthy.get_service_pods", return_value=_healthy_pods("galley")):
        result: bool = target.collect()

    assert result is True


def test_galley_replicas_description() -> None:
    """GalleyReplicas should have a description about replica count."""
    target: GalleyReplicas = GalleyReplicas(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Number of Galley pod replicas"


def test_galley_replicas_unit() -> None:
    """GalleyReplicas should report its unit as « pods »."""
    target: GalleyReplicas = GalleyReplicas(_make_config(), _make_terminal(), _make_logger())
    assert target.unit == "pods"


def test_galley_replicas_count() -> None:
    """GalleyReplicas should return the right count."""
    target: GalleyReplicas = GalleyReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.galley.replicas.get_service_pods", return_value=_healthy_pods("galley", 2)):
        result: int = target.collect()

    assert result == 2


# ===========================================================================
# Cannon: healthy and replicas
# ===========================================================================

def test_cannon_healthy_description() -> None:
    """CannonHealthy should have a reasonable description."""
    target: CannonHealthy = CannonHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Cannon (WebSocket push) - all replicas running"


def test_cannon_healthy_returns_true() -> None:
    """Healthy pods mean CannonHealthy returns True."""
    target: CannonHealthy = CannonHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.cannon.healthy.get_service_pods", return_value=_healthy_pods("cannon")):
        result: bool = target.collect()

    assert result is True


def test_cannon_replicas_count() -> None:
    """CannonReplicas should return the right count."""
    target: CannonReplicas = CannonReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.cannon.replicas.get_service_pods", return_value=_healthy_pods("cannon", 4)):
        result: int = target.collect()

    assert result == 4


# ===========================================================================
# Cargohold: healthy and replicas
# ===========================================================================

def test_cargohold_healthy_description() -> None:
    """CargoholdHealthy should have a reasonable description."""
    target: CargoholdHealthy = CargoholdHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Cargohold (asset storage) - all replicas running"


def test_cargohold_healthy_returns_true() -> None:
    """Healthy pods mean CargoholdHealthy returns True."""
    target: CargoholdHealthy = CargoholdHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.cargohold.healthy.get_service_pods", return_value=_healthy_pods("cargohold")):
        result: bool = target.collect()

    assert result is True


def test_cargohold_replicas_count() -> None:
    """CargoholdReplicas should return the right count."""
    target: CargoholdReplicas = CargoholdReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.cargohold.replicas.get_service_pods", return_value=_healthy_pods("cargohold", 2)):
        result: int = target.collect()

    assert result == 2


# ===========================================================================
# Gundeck: healthy and replicas
# ===========================================================================

def test_gundeck_healthy_description() -> None:
    """GundeckHealthy should have a reasonable description."""
    target: GundeckHealthy = GundeckHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Gundeck (push notifications) - all replicas running"


def test_gundeck_healthy_returns_true() -> None:
    """Healthy pods mean GundeckHealthy returns True."""
    target: GundeckHealthy = GundeckHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.gundeck.healthy.get_service_pods", return_value=_healthy_pods("gundeck")):
        result: bool = target.collect()

    assert result is True


def test_gundeck_replicas_count() -> None:
    """GundeckReplicas should return the right count."""
    target: GundeckReplicas = GundeckReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.gundeck.replicas.get_service_pods", return_value=_healthy_pods("gundeck", 2)):
        result: int = target.collect()

    assert result == 2


# ===========================================================================
# Spar: healthy and replicas
# ===========================================================================

def test_spar_healthy_description() -> None:
    """SparHealthy should have a reasonable description."""
    target: SparHealthy = SparHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Spar (SSO/SCIM) - all replicas running"


def test_spar_healthy_returns_true() -> None:
    """Healthy pods mean SparHealthy returns True."""
    target: SparHealthy = SparHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.spar.healthy.get_service_pods", return_value=_healthy_pods("spar")):
        result: bool = target.collect()

    assert result is True


def test_spar_replicas_count() -> None:
    """SparReplicas should return the right count."""
    target: SparReplicas = SparReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.spar.replicas.get_service_pods", return_value=_healthy_pods("spar", 2)):
        result: int = target.collect()

    assert result == 2


# ===========================================================================
# Nginz: healthy and replicas
# ===========================================================================

def test_nginz_healthy_description() -> None:
    """NginzHealthy should have a reasonable description."""
    target: NginzHealthy = NginzHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Nginz (API gateway) - all replicas running"


def test_nginz_healthy_returns_true() -> None:
    """Healthy pods mean NginzHealthy returns True."""
    target: NginzHealthy = NginzHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.nginz.healthy.get_service_pods", return_value=_healthy_pods("nginz")):
        result: bool = target.collect()

    assert result is True


def test_nginz_replicas_count() -> None:
    """NginzReplicas should return the right count."""
    target: NginzReplicas = NginzReplicas(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.nginz.replicas.get_service_pods", return_value=_healthy_pods("nginz", 2)):
        result: int = target.collect()

    assert result == 2


# ===========================================================================
# Background Worker healthy only (single-replica service)
# ===========================================================================

def test_background_worker_healthy_description() -> None:
    """BackgroundWorkerHealthy should have a reasonable description."""
    target: BackgroundWorkerHealthy = BackgroundWorkerHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Background Worker - all replicas running"


def test_background_worker_healthy_returns_true() -> None:
    """BackgroundWorkerHealthy should return True when the pod is healthy."""
    target: BackgroundWorkerHealthy = BackgroundWorkerHealthy(_make_config(), _make_terminal(), _make_logger())

    # background-worker uses hyphenated name for Kubernetes pod naming
    with patch("src.targets.wire_services.background_worker.healthy.get_service_pods", return_value=_healthy_pods("background-worker", 1)):
        result: bool = target.collect()

    assert result is True


def test_background_worker_healthy_dynamic_description() -> None:
    """BackgroundWorkerHealthy should update its description with replica count."""
    target: BackgroundWorkerHealthy = BackgroundWorkerHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.background_worker.healthy.get_service_pods", return_value=_healthy_pods("background-worker", 1)):
        target.collect()

    assert target._dynamic_description == "Background Worker - 1 replica running"


# ===========================================================================
# SFTd healthy only (single-replica service)
# ===========================================================================

def test_sftd_healthy_description() -> None:
    """SftdHealthy should have a reasonable description."""
    target: SftdHealthy = SftdHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "SFTd (conference calling) - all replicas running"


def test_sftd_healthy_returns_true() -> None:
    """SftdHealthy should return True when the pod is healthy."""
    target: SftdHealthy = SftdHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.sftd.healthy.get_service_pods", return_value=_healthy_pods("sftd", 1)):
        result: bool = target.collect()

    assert result is True


# ===========================================================================
# Coturn healthy only (single-replica service)
# ===========================================================================

def test_coturn_healthy_description() -> None:
    """CoturnHealthy should have a reasonable description."""
    target: CoturnHealthy = CoturnHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Coturn (TURN server) - all replicas running"


def test_coturn_healthy_returns_true() -> None:
    """CoturnHealthy should return True when the pod is healthy."""
    target: CoturnHealthy = CoturnHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.coturn.healthy.get_service_pods", return_value=_healthy_pods("coturn", 1)):
        result: bool = target.collect()

    assert result is True


# ===========================================================================
# Webapp healthy only (single-replica service)
# ===========================================================================

def test_webapp_healthy_description() -> None:
    """WebappHealthy should have a reasonable description."""
    target: WebappHealthy = WebappHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Webapp - all replicas running"


def test_webapp_healthy_returns_true() -> None:
    """WebappHealthy should return True when the pod is healthy."""
    target: WebappHealthy = WebappHealthy(_make_config(), _make_terminal(), _make_logger())

    with patch("src.targets.wire_services.webapp.healthy.get_service_pods", return_value=_healthy_pods("webapp", 1)):
        result: bool = target.collect()

    assert result is True


# ===========================================================================
# Team Settings healthy only (single-replica service)
# ===========================================================================

def test_team_settings_healthy_description() -> None:
    """TeamSettingsHealthy should have a reasonable description."""
    target: TeamSettingsHealthy = TeamSettingsHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Team Settings - all replicas running"


def test_team_settings_healthy_returns_true() -> None:
    """TeamSettingsHealthy should return True when the pod is healthy."""
    target: TeamSettingsHealthy = TeamSettingsHealthy(_make_config(), _make_terminal(), _make_logger())

    # team-settings uses hyphenated name for Kubernetes pod naming
    with patch("src.targets.wire_services.team_settings.healthy.get_service_pods", return_value=_healthy_pods("team-settings", 1)):
        result: bool = target.collect()

    assert result is True


# ===========================================================================
# Account Pages healthy only (single-replica service)
# ===========================================================================

def test_account_pages_healthy_description() -> None:
    """AccountPagesHealthy should have a reasonable description."""
    target: AccountPagesHealthy = AccountPagesHealthy(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Account Pages - all replicas running"


def test_account_pages_healthy_returns_true() -> None:
    """AccountPagesHealthy should return True when the pod is healthy."""
    target: AccountPagesHealthy = AccountPagesHealthy(_make_config(), _make_terminal(), _make_logger())

    # account-pages uses hyphenated name for Kubernetes pod naming
    with patch("src.targets.wire_services.account_pages.healthy.get_service_pods", return_value=_healthy_pods("account-pages", 1)):
        result: bool = target.collect()

    assert result is True


# ===========================================================================
# Helpers for SSH-based and kubectl-based targets
# ===========================================================================

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


# ===========================================================================
# AssetHost
# ===========================================================================

def test_asset_host_description() -> None:
    """AssetHost should have a reasonable description."""
    target: AssetHost = AssetHost(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Asset host HTTP service running"


def test_asset_host_responds_200() -> None:
    """AssetHost returns True for a 200 response."""
    target: AssetHost = AssetHost(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("200")):
        result: bool = target.collect()

    assert result is True


def test_asset_host_responds_404() -> None:
    """AssetHost returns True for non-5xx codes; the server is responding."""
    target: AssetHost = AssetHost(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("404")):
        result: bool = target.collect()

    assert result is True


def test_asset_host_responds_500() -> None:
    """AssetHost returns False for a 500 error."""
    target: AssetHost = AssetHost(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("500")):
        result: bool = target.collect()

    assert result is False


def test_asset_host_no_response() -> None:
    """AssetHost returns False if we can't parse an HTTP code."""
    target: AssetHost = AssetHost(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        result: bool = target.collect()

    assert result is False


# ===========================================================================
# IngressResponse
# ===========================================================================

def test_ingress_response_description() -> None:
    """IngressResponse should have a reasonable description."""
    target: IngressResponse = IngressResponse(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Ingress controller response test"


def test_ingress_response_200() -> None:
    """IngressResponse returns True when it gets a 200."""
    target: IngressResponse = IngressResponse(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("200")):
        result: bool = target.collect()

    assert result is True


def test_ingress_response_503() -> None:
    """IngressResponse returns False for a 503 error."""
    target: IngressResponse = IngressResponse(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("503")):
        result: bool = target.collect()

    assert result is False


def test_ingress_response_non_numeric() -> None:
    """IngressResponse returns False if we can't parse an HTTP code."""
    target: IngressResponse = IngressResponse(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("timeout")):
        result: bool = target.collect()

    assert result is False


# ===========================================================================
# ServiceList
# ===========================================================================

def test_service_list_description() -> None:
    """ServiceList should have a reasonable description."""
    target: ServiceList = ServiceList(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "List of deployed Wire services"


def test_service_list_returns_sorted_names() -> None:
    """ServiceList should return service names sorted and comma-separated."""
    deployments: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig"}, "spec": {"replicas": 3}, "status": {"readyReplicas": 3}},
        {"metadata": {"name": "galley"}, "spec": {"replicas": 2}, "status": {"readyReplicas": 2}},
    ]}
    statefulsets: dict[str, Any] = {"items": [
        {"metadata": {"name": "cassandra"}, "spec": {"replicas": 3}, "status": {"readyReplicas": 3}},
    ]}
    daemonsets: dict[str, Any] = {"items": []}
    target: ServiceList = ServiceList(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), deployments),
        (_kubectl_cmd_result(), statefulsets),
        (_kubectl_cmd_result(), daemonsets),
    ]):
        result: str = target.collect()

    assert "brig" in result
    assert "cassandra" in result
    assert "galley" in result


def test_service_list_detects_under_replicated() -> None:
    """ServiceList should detect when services don't have enough replicas."""
    deployments: dict[str, Any] = {"items": [
        {"metadata": {"name": "brig"}, "spec": {"replicas": 3}, "status": {"readyReplicas": 1}},
    ]}
    empty: dict[str, Any] = {"items": []}
    target: ServiceList = ServiceList(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), deployments),
        (_kubectl_cmd_result(), empty),
        (_kubectl_cmd_result(), empty),
    ]):
        target.collect()

    assert "under-replicated" in target._health_info
    assert "brig" in target._health_info


def test_service_list_null_data_raises() -> None:
    """ServiceList should raise if kubectl returns None."""
    target: ServiceList = ServiceList(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ===========================================================================
# StatusEndpoints
# ===========================================================================

def test_status_endpoints_description() -> None:
    """StatusEndpoints should have a reasonable description."""
    target: StatusEndpoints = StatusEndpoints(_make_config(), _make_terminal(), _make_logger())
    assert "/i/status" in target.description


def test_status_endpoints_all_responding() -> None:
    """StatusEndpoints should report 6/6 when all services respond."""
    target: StatusEndpoints = StatusEndpoints(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("200")):
        result: str = target.collect()

    assert "6/6" in result
    assert "6/6 healthy" in target._health_info


def test_status_endpoints_some_down() -> None:
    """StatusEndpoints should count how many services actually respond."""
    call_count: int = 0

    def _alternating(*args: object, **kwargs: object) -> CommandResult:
        nonlocal call_count
        call_count += 1
        if call_count <= 4:
            return _ssh_cmd_result("200")
        return _ssh_cmd_result("503")

    target: StatusEndpoints = StatusEndpoints(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", side_effect=_alternating):
        result: str = target.collect()

    assert "4/6" in result


def test_status_endpoints_unique_urls() -> None:
    """Each service must hit a different URL (not the same path 6 times)."""
    from src.targets.wire_services.status_endpoints import _STATUS_SERVICES

    # Every service entry must have a unique path that includes the service name
    paths: list[str] = [svc["path"] for svc in _STATUS_SERVICES]
    assert len(paths) == len(set(paths)), (
        f"Expected all unique paths but got duplicates: {paths}"
    )

    # Each path must contain its service name so it routes to the right backend
    for svc in _STATUS_SERVICES:
        assert svc["name"] in svc["path"], (
            f"Path {svc['path']} does not contain service name {svc['name']}"
        )


def test_status_endpoints_all_erroring_no_raise() -> None:
    """StatusEndpoints should NOT raise when all services return 5xx.

    5xx means the service is reachable but returning a server error (e.g.
    during a rolling upgrade).  Only genuinely unreachable services (code 0)
    should cause a RuntimeError.
    """
    target: StatusEndpoints = StatusEndpoints(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("503")):
        result: str = target.collect()

    assert "0/6" in result
    assert "erroring" in target._health_info


def test_status_endpoints_none_respond_raises() -> None:
    """StatusEndpoints should raise if nothing responds at all."""
    target: StatusEndpoints = StatusEndpoints(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("000")):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ===========================================================================
# WebappHttp
# ===========================================================================

def test_webapp_http_description() -> None:
    """WebappHttp should have a reasonable description."""
    target: WebappHttp = WebappHttp(_make_config(), _make_terminal(), _make_logger())
    assert target.description == "Webapp HTTP accessibility"


def test_webapp_http_accessible() -> None:
    """WebappHttp returns True for a 200 response."""
    target: WebappHttp = WebappHttp(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("200")):
        result: bool = target.collect()

    assert result is True


def test_webapp_http_redirect() -> None:
    """WebappHttp returns True for redirects; the server's still there."""
    target: WebappHttp = WebappHttp(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("301")):
        result: bool = target.collect()

    assert result is True


def test_webapp_http_server_error() -> None:
    """WebappHttp returns False for a 500 error."""
    target: WebappHttp = WebappHttp(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("500")):
        result: bool = target.collect()

    assert result is False


def test_webapp_http_non_numeric() -> None:
    """WebappHttp returns False if we can't parse an HTTP code."""
    target: WebappHttp = WebappHttp(_make_config(), _make_terminal(), _make_logger())

    with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result("")):
        result: bool = target.collect()

    assert result is False
