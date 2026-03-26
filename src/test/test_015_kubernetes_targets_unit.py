"""Unit tests for Kubernetes target implementations.

Tests a bunch of Kubernetes targets: NodeCount, AllReady (nodes), K8sVersion,
UnhealthyCount, TotalRunning, CertificatesAllReady, and MetricsApi. Each target's
collect() method gets tested by mocking kubectl_get or kubectl_raw at the
base_target module level.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch, call

from src.lib.command import CommandResult
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.targets.kubernetes.nodes.count import NodeCount
from src.targets.kubernetes.nodes.all_ready import AllReady
from src.targets.kubernetes.nodes.k8s_version import K8sVersion
from src.targets.kubernetes.pods.unhealthy_count import UnhealthyCount
from src.targets.kubernetes.pods.total_running import TotalRunning
from src.targets.kubernetes.certificates.all_ready import CertificatesAllReady
from src.targets.kubernetes.metrics_api import MetricsApi
from src.targets.kubernetes.nodes.sft_node_labels import SftNodeLabels
from src.targets.kubernetes.nodes.container_runtime import ContainerRuntime
from src.targets.kubernetes.certificates.count import CertificateCount
from src.targets.kubernetes.etcd.health import EtcdHealth
from src.targets.kubernetes.pods.restart_counts import RestartCounts
from src.targets.kubernetes.pods.coturn_memory_limits import CoturnMemoryLimits
from src.targets.kubernetes.pvc.all_bound import PvcAllBound
from src.targets.kubernetes.ingress.list import IngressList
from src.targets.kubernetes.configmaps import KubernetesConfigmaps
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_terminal() -> Terminal:
    """Make a quiet terminal to keep test output clean."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Make a logger that stays silent."""
    return Logger(level=LogLevel.ERROR)


def _kubectl_cmd_result(stdout: str = "{}") -> CommandResult:
    """Make a fake successful kubectl command result."""
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
    """Make a fake successful SSH command result."""
    return CommandResult(
        command="ssh test",
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )


def _make_node(name: str, ready: bool = True, version: str = "v1.28.5") -> dict[str, Any]:
    """Make a fake Kubernetes node for tests."""
    return {
        "metadata": {"name": name},
        "status": {
            "conditions": [
                {"type": "MemoryPressure", "status": "False"},
                {"type": "DiskPressure", "status": "False"},
                {"type": "Ready", "status": "True" if ready else "False"},
            ],
            "nodeInfo": {
                "kubeletVersion": version,
            },
        },
    }


def _make_pod(name: str, phase: str = "Running", restart_count: int = 0) -> dict[str, Any]:
    """Make a fake Kubernetes pod for tests."""
    pod: dict[str, Any] = {
        "metadata": {"name": name, "namespace": "default"},
        "status": {"phase": phase},
    }
    if restart_count > 0:
        pod["status"]["containerStatuses"] = [
            {"name": "main", "restartCount": restart_count},
        ]
    return pod


def _make_cert(name: str, ready: bool = True) -> dict[str, Any]:
    """Make a fake cert-manager certificate for tests."""
    return {
        "metadata": {"name": name, "namespace": "wire"},
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True" if ready else "False"},
            ],
        },
    }


# ---------------------------------------------------------------------------
# NodeCount
# ---------------------------------------------------------------------------

def test_node_count_description() -> None:
    """Check that NodeCount has the right description."""
    target: NodeCount = NodeCount(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "Number of active Kubernetes nodes"


def test_node_count_unit() -> None:
    """NodeCount should report its unit as nodes."""
    target: NodeCount = NodeCount(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == "nodes"


def test_node_count_collect_three_nodes() -> None:
    """NodeCount should return the count of nodes."""
    data: dict[str, Any] = {
        "items": [_make_node("node-1"), _make_node("node-2"), _make_node("node-3")],
    }
    target: NodeCount = NodeCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 3


def test_node_count_collect_empty_cluster() -> None:
    """NodeCount should return 0 when there are no nodes."""
    data: dict[str, Any] = {"items": []}
    target: NodeCount = NodeCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_node_count_collect_none_data_raises() -> None:
    """NodeCount should raise RuntimeError if kubectl returns nothing."""
    target: NodeCount = NodeCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "Failed to get nodes" in str(error)


def test_node_count_collect_missing_items_key() -> None:
    """NodeCount should return 0 if the items key is missing."""
    data: dict[str, Any] = {}
    target: NodeCount = NodeCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


# ---------------------------------------------------------------------------
# AllReady (nodes)
# ---------------------------------------------------------------------------

def test_all_ready_description() -> None:
    """Check that AllReady has the right description."""
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "All Kubernetes nodes are in Ready state"


def test_all_ready_unit() -> None:
    """AllReady should have an empty unit."""
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_all_ready_collect_all_ready() -> None:
    """AllReady should return True when all nodes are ready."""
    data: dict[str, Any] = {
        "items": [_make_node("n1", ready=True), _make_node("n2", ready=True)],
    }
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


def test_all_ready_collect_one_not_ready() -> None:
    """AllReady should return False if any node isn't ready."""
    data: dict[str, Any] = {
        "items": [_make_node("n1", ready=True), _make_node("n2", ready=False)],
    }
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is False


def test_all_ready_collect_empty_nodes() -> None:
    """AllReady returns True for no nodes (vacuously true)."""
    data: dict[str, Any] = {"items": []}
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


def test_all_ready_collect_node_without_conditions() -> None:
    """AllReady should return False for a node with no conditions."""
    node_no_conditions: dict[str, Any] = {
        "metadata": {"name": "broken-node"},
        "status": {"conditions": []},
    }
    data: dict[str, Any] = {"items": [node_no_conditions]}
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is False


def test_all_ready_collect_none_data_raises() -> None:
    """AllReady should raise RuntimeError if kubectl returns nothing."""
    target: AllReady = AllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "Failed to get nodes" in str(error)


# ---------------------------------------------------------------------------
# K8sVersion
# ---------------------------------------------------------------------------

def test_k8s_version_description() -> None:
    """Check that K8sVersion has the right description."""
    target: K8sVersion = K8sVersion(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "Kubernetes cluster version"


def test_k8s_version_unit() -> None:
    """K8sVersion should have an empty unit."""
    target: K8sVersion = K8sVersion(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_k8s_version_collect_returns_version() -> None:
    """K8sVersion should grab the version from the first node."""
    data: dict[str, Any] = {
        "items": [_make_node("n1", version="v1.28.5"), _make_node("n2", version="v1.28.4")],
    }
    target: K8sVersion = K8sVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: str = target.collect()

    # just grabs the first node's version
    assert result == "v1.28.5"


def test_k8s_version_collect_no_nodes_raises() -> None:
    """K8sVersion should raise RuntimeError if there are no nodes."""
    data: dict[str, Any] = {"items": []}
    target: K8sVersion = K8sVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "No nodes found" in str(error)


def test_k8s_version_collect_missing_version_field() -> None:
    """K8sVersion should return 'unknown' when nodeInfo lacks kubeletVersion."""
    node_no_version: dict[str, Any] = {
        "metadata": {"name": "n1"},
        "status": {},
    }
    data: dict[str, Any] = {"items": [node_no_version]}
    target: K8sVersion = K8sVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: str = target.collect()

    assert result == "unknown"


def test_k8s_version_collect_none_data_raises() -> None:
    """K8sVersion should raise RuntimeError when kubectl returns nothing."""
    target: K8sVersion = K8sVersion(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "Failed to get nodes" in str(error)


# ---------------------------------------------------------------------------
# UnhealthyCount
# ---------------------------------------------------------------------------

def test_unhealthy_count_description() -> None:
    """Check that UnhealthyCount has the right description."""
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "Number of pods not in Running or Completed state"


def test_unhealthy_count_unit() -> None:
    """UnhealthyCount should report its unit as pods."""
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == "pods"


def test_unhealthy_count_collect_all_healthy() -> None:
    """UnhealthyCount should return 0 when all pods are Running or Succeeded."""
    data: dict[str, Any] = {
        "items": [
            _make_pod("p1", "Running"),
            _make_pod("p2", "Succeeded"),
            _make_pod("p3", "Running"),
        ],
    }
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_unhealthy_count_collect_some_unhealthy() -> None:
    """UnhealthyCount should count pods not in Running or Succeeded phase."""
    data: dict[str, Any] = {
        "items": [
            _make_pod("p1", "Running"),
            _make_pod("p2", "Failed"),
            _make_pod("p3", "Pending"),
            _make_pod("p4", "Succeeded"),
            _make_pod("p5", "CrashLoopBackOff"),
        ],
    }
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    # Failed, Pending, CrashLoopBackOff are all unhealthy
    assert result == 3


def test_unhealthy_count_collect_empty_pods() -> None:
    """UnhealthyCount should return 0 when no pods exist."""
    data: dict[str, Any] = {"items": []}
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_unhealthy_count_collect_none_data_raises() -> None:
    """UnhealthyCount raises RuntimeError when kubectl returns None."""
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "Failed to get pods" in str(error)


def test_unhealthy_count_collect_pod_missing_phase() -> None:
    """UnhealthyCount treats pods without phase as unhealthy."""
    data: dict[str, Any] = {
        "items": [
            {"metadata": {"name": "p1"}, "status": {}},
        ],
    }
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    # Empty string phase is not in ("Running", "Succeeded")
    assert result == 1


def test_unhealthy_count_uses_all_namespaces() -> None:
    """UnhealthyCount should query all namespaces."""
    data: dict[str, Any] = {"items": []}
    target: UnhealthyCount = UnhealthyCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)) as mock_kube:
        target.collect()

    # Verify all_namespaces=True was passed
    call_kwargs: dict[str, Any] = mock_kube.call_args[1]
    assert call_kwargs["all_namespaces"] is True


# ---------------------------------------------------------------------------
# TotalRunning
# ---------------------------------------------------------------------------

def test_total_running_description() -> None:
    """Check that TotalRunning has the right description."""
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "Total running pods across all namespaces"


def test_total_running_unit() -> None:
    """TotalRunning should report its unit as pods."""
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == "pods"


def test_total_running_collect_counts_running() -> None:
    """TotalRunning should count only Running pods."""
    data: dict[str, Any] = {
        "items": [
            _make_pod("p1", "Running"),
            _make_pod("p2", "Failed"),
            _make_pod("p3", "Running"),
            _make_pod("p4", "Succeeded"),
            _make_pod("p5", "Running"),
        ],
    }
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 3


def test_total_running_collect_no_running() -> None:
    """TotalRunning should return 0 when no pods are Running."""
    data: dict[str, Any] = {
        "items": [
            _make_pod("p1", "Succeeded"),
            _make_pod("p2", "Failed"),
        ],
    }
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_total_running_collect_empty_pods() -> None:
    """TotalRunning should return 0 when no pods exist."""
    data: dict[str, Any] = {"items": []}
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_total_running_collect_none_data_raises() -> None:
    """TotalRunning raises RuntimeError when kubectl returns None."""
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "Failed to get pods" in str(error)


def test_total_running_uses_all_namespaces() -> None:
    """TotalRunning should query all namespaces."""
    data: dict[str, Any] = {"items": []}
    target: TotalRunning = TotalRunning(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)) as mock_kube:
        target.collect()

    call_kwargs: dict[str, Any] = mock_kube.call_args[1]
    assert call_kwargs["all_namespaces"] is True


# ---------------------------------------------------------------------------
# CertificatesAllReady
# ---------------------------------------------------------------------------

def test_certificates_all_ready_description() -> None:
    """Check that CertificatesAllReady has the right description."""
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "All TLS certificates are in Ready state"


def test_certificates_all_ready_unit() -> None:
    """CertificatesAllReady should have an empty unit."""
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_certificates_all_ready_collect_all_ready() -> None:
    """CertificatesAllReady should return True when all certs are ready."""
    data: dict[str, Any] = {
        "items": [_make_cert("cert-1", ready=True), _make_cert("cert-2", ready=True)],
    }
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


def test_certificates_all_ready_collect_one_not_ready() -> None:
    """CertificatesAllReady should return False when one cert is not ready."""
    data: dict[str, Any] = {
        "items": [_make_cert("cert-1", ready=True), _make_cert("cert-2", ready=False)],
    }
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is False


def test_certificates_all_ready_collect_empty_returns_true() -> None:
    """CertificatesAllReady returns True when no certs exist (vacuously true)."""
    data: dict[str, Any] = {"items": []}
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


def test_certificates_all_ready_collect_fallback_to_short_name() -> None:
    """CertificatesAllReady should fall back to 'certificates' when CRD name fails."""
    data: dict[str, Any] = {
        "items": [_make_cert("cert-1", ready=True)],
    }
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())

    # First call with full CRD name returns None, second with short name succeeds
    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), None),
        (_kubectl_cmd_result(), data),
    ]) as mock_kube:
        result: bool = target.collect()

    assert result is True
    # Verify two calls were made
    assert mock_kube.call_count == 2
    # First call used full CRD name
    first_call_kwargs: dict[str, Any] = mock_kube.call_args_list[0][1]
    assert first_call_kwargs["resource"] == "certificates.cert-manager.io"
    # Second call used short name
    second_call_kwargs: dict[str, Any] = mock_kube.call_args_list[1][1]
    assert second_call_kwargs["resource"] == "certificates"


def test_certificates_all_ready_collect_both_fail_raises() -> None:
    """CertificatesAllReady should raise when both CRD names fail."""
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as error:
            assert "cert-manager" in str(error).lower()


def test_certificates_all_ready_collect_cert_without_conditions() -> None:
    """CertificatesAllReady returns False for cert without conditions."""
    cert_no_conditions: dict[str, Any] = {
        "metadata": {"name": "broken-cert"},
        "status": {"conditions": []},
    }
    data: dict[str, Any] = {"items": [cert_no_conditions]}
    target: CertificatesAllReady = CertificatesAllReady(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is False


# ---------------------------------------------------------------------------
# MetricsApi
# ---------------------------------------------------------------------------

def test_metrics_api_description() -> None:
    """Check that MetricsApi has the right description."""
    target: MetricsApi = MetricsApi(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.description == "Kubernetes Metrics API is available (kubectl top)"


def test_metrics_api_unit() -> None:
    """MetricsApi should have an empty unit."""
    target: MetricsApi = MetricsApi(make_minimal_config(), _make_terminal(), _make_logger())
    assert target.unit == ""


def test_metrics_api_collect_success() -> None:
    """MetricsApi should return True when kubectl top succeeds."""
    mock_result: CommandResult = CommandResult(
        command="kubectl top nodes --no-headers",
        exit_code=0,
        stdout="node-1  100m  5%  512Mi  10%\n",
        stderr="",
        duration_seconds=0.2,
        success=True,
        timed_out=False,
    )
    target: MetricsApi = MetricsApi(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_raw", return_value=mock_result):
        result: bool = target.collect()

    assert result is True


def test_metrics_api_collect_failure() -> None:
    """MetricsApi should return False when kubectl top fails."""
    mock_result: CommandResult = CommandResult(
        command="kubectl top nodes --no-headers",
        exit_code=1,
        stdout="",
        stderr="error: Metrics API not available",
        duration_seconds=0.1,
        success=False,
        timed_out=False,
    )
    target: MetricsApi = MetricsApi(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_raw", return_value=mock_result):
        result: bool = target.collect()

    assert result is False


def test_metrics_api_collect_passes_correct_args() -> None:
    """MetricsApi should pass the correct arguments to kubectl_raw."""
    mock_result: CommandResult = CommandResult(
        command="kubectl top nodes --no-headers",
        exit_code=0,
        stdout="node-1  100m  5%\n",
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )
    target: MetricsApi = MetricsApi(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_raw", return_value=mock_result) as mock_raw:
        target.collect()

    # make_minimal_config() has databases.ssh_key="" so ssh_target is None
    # and docker_image is "" (no SSH routing needed for kubectl).
    mock_raw.assert_called_once_with(
        args=["top", "nodes", "--no-headers"],
        timeout=30,
        context="",
        ssh_target=None,
        docker_image="",
        admin_home="/home/deploy",
    )


# ---------------------------------------------------------------------------
# SftNodeLabels
# ---------------------------------------------------------------------------

def test_sft_node_labels_description() -> None:
    """Check that SftNodeLabels has the right description."""
    target: SftNodeLabels = SftNodeLabels(make_minimal_config(), _make_terminal(), _make_logger())
    assert "SFT" in target.description


def test_sft_node_labels_collect_finds_labeled_nodes() -> None:
    """SftNodeLabels should count nodes with wire.link/role=sft."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "node-1", "labels": {"wire.link/role": "sft"}}},
        {"metadata": {"name": "node-2", "labels": {"wire.link/role": "worker"}}},
        {"metadata": {"name": "node-3", "labels": {"wire.link/role": "sft"}}},
    ]}
    target: SftNodeLabels = SftNodeLabels(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 2


def test_sft_node_labels_collect_no_sft_nodes() -> None:
    """SftNodeLabels should return 0 when no nodes have SFT labels."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "node-1", "labels": {}}},
    ]}
    target: SftNodeLabels = SftNodeLabels(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_sft_node_labels_collect_none_data_raises() -> None:
    """SftNodeLabels should raise when kubectl returns None."""
    target: SftNodeLabels = SftNodeLabels(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# ContainerRuntime
# ---------------------------------------------------------------------------

def test_container_runtime_description() -> None:
    """Check that ContainerRuntime has the right description."""
    target: ContainerRuntime = ContainerRuntime(make_minimal_config(), _make_terminal(), _make_logger())
    assert "container runtime" in target.description.lower()


def test_container_runtime_collect_single_runtime() -> None:
    """ContainerRuntime should return the runtime when all nodes use the same one."""
    data: dict[str, Any] = {"items": [
        _make_node("node-1"),
        _make_node("node-2"),
    ]}
    # Add containerRuntimeVersion to nodeInfo
    for item in data["items"]:
        item["status"]["nodeInfo"] = {"containerRuntimeVersion": "containerd://1.7.2"}

    target: ContainerRuntime = ContainerRuntime(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: str = target.collect()

    assert result == "containerd://1.7.2"


def test_container_runtime_collect_mixed_runtimes() -> None:
    """ContainerRuntime reports mixed runtimes."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "n1"}, "status": {"nodeInfo": {"containerRuntimeVersion": "containerd://1.7.2"}}},
        {"metadata": {"name": "n2"}, "status": {"nodeInfo": {"containerRuntimeVersion": "cri-o://1.28.0"}}},
    ]}
    target: ContainerRuntime = ContainerRuntime(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: str = target.collect()

    assert "containerd://1.7.2" in result
    assert "cri-o://1.28.0" in result


def test_container_runtime_collect_no_nodes_raises() -> None:
    """ContainerRuntime should raise when cluster has no nodes."""
    data: dict[str, Any] = {"items": []}
    target: ContainerRuntime = ContainerRuntime(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# CertificateCount
# ---------------------------------------------------------------------------

def test_certificate_count_description() -> None:
    """Check that CertificateCount has the right description."""
    target: CertificateCount = CertificateCount(make_minimal_config(), _make_terminal(), _make_logger())
    assert "cert-manager" in target.description.lower()


def test_certificate_count_collect_returns_count() -> None:
    """CertificateCount returns the number of certificate resources."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "cert-1"}},
        {"metadata": {"name": "cert-2"}},
        {"metadata": {"name": "cert-3"}},
    ]}
    target: CertificateCount = CertificateCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 3


def test_certificate_count_collect_empty() -> None:
    """CertificateCount should return 0 when no certificates exist."""
    data: dict[str, Any] = {"items": []}
    target: CertificateCount = CertificateCount(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_certificate_count_collect_fallback_on_none() -> None:
    """CertificateCount should tries shorthand when CRD returns None."""
    data: dict[str, Any] = {"items": [{"metadata": {"name": "cert-1"}}]}
    target: CertificateCount = CertificateCount(make_minimal_config(), _make_terminal(), _make_logger())

    # First call returns None (CRD not found), second returns data
    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), None),
        (_kubectl_cmd_result(), data),
    ]):
        result: int = target.collect()

    assert result == 1


# ---------------------------------------------------------------------------
# RestartCounts
# ---------------------------------------------------------------------------

def test_restart_counts_description() -> None:
    """Check that RestartCounts has the right description."""
    target: RestartCounts = RestartCounts(make_minimal_config(), _make_terminal(), _make_logger())
    assert "restart" in target.description.lower()


def test_restart_counts_collect_no_high_restarts() -> None:
    """RestartCounts should return 0 when all pods have low restart counts."""
    data: dict[str, Any] = {"items": [
        _make_pod("pod-1", "Running", restart_count=2),
        _make_pod("pod-2", "Running", restart_count=0),
    ]}
    target: RestartCounts = RestartCounts(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


def test_restart_counts_collect_some_high_restarts() -> None:
    """RestartCounts should count pods above the threshold."""
    data: dict[str, Any] = {"items": [
        _make_pod("crasher", "Running", restart_count=50),
        _make_pod("healthy", "Running", restart_count=1),
        _make_pod("oom-pod", "Running", restart_count=10),
    ]}
    target: RestartCounts = RestartCounts(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 2


def test_restart_counts_collect_empty_pods() -> None:
    """RestartCounts returns 0 for empty pod list."""
    data: dict[str, Any] = {"items": []}
    target: RestartCounts = RestartCounts(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: int = target.collect()

    assert result == 0


# ---------------------------------------------------------------------------
# CoturnMemoryLimits
# ---------------------------------------------------------------------------

def test_coturn_memory_limits_description() -> None:
    """Check that CoturnMemoryLimits has the right description."""
    target: CoturnMemoryLimits = CoturnMemoryLimits(make_minimal_config(), _make_terminal(), _make_logger())
    assert "coturn" in target.description.lower()


def test_coturn_memory_limits_collect_all_limited() -> None:
    """CoturnMemoryLimits should return True when all containers have limits."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "coturn-0", "namespace": "wire"},
         "spec": {"containers": [{"name": "coturn", "resources": {"limits": {"memory": "512Mi"}}}]}},
    ]}
    target: CoturnMemoryLimits = CoturnMemoryLimits(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


def test_coturn_memory_limits_collect_missing_limit() -> None:
    """CoturnMemoryLimits should return False when a container lacks memory limit."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "coturn-0", "namespace": "wire"},
         "spec": {"containers": [{"name": "coturn", "resources": {}}]}},
    ]}
    target: CoturnMemoryLimits = CoturnMemoryLimits(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is False


def test_coturn_memory_limits_collect_no_pods_returns_true() -> None:
    """CoturnMemoryLimits should return True when no coturn pods exist."""
    empty: dict[str, Any] = {"items": []}
    target: CoturnMemoryLimits = CoturnMemoryLimits(make_minimal_config(), _make_terminal(), _make_logger())

    # All three selectors return empty
    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), empty)):
        result: bool = target.collect()

    assert result is True


# ---------------------------------------------------------------------------
# PvcAllBound
# ---------------------------------------------------------------------------

def test_pvc_all_bound_description() -> None:
    """Check that PvcAllBound has the right description."""
    target: PvcAllBound = PvcAllBound(make_minimal_config(), _make_terminal(), _make_logger())
    assert "PersistentVolumeClaim" in target.description


def test_pvc_all_bound_collect_all_bound() -> None:
    """PvcAllBound should return True when all PVCs are bound."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "pvc-1", "namespace": "wire"}, "status": {"phase": "Bound"}},
        {"metadata": {"name": "pvc-2", "namespace": "wire"}, "status": {"phase": "Bound"}},
    ]}
    target: PvcAllBound = PvcAllBound(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


def test_pvc_all_bound_collect_one_pending() -> None:
    """PvcAllBound should return False when a PVC is not bound."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "pvc-1", "namespace": "wire"}, "status": {"phase": "Bound"}},
        {"metadata": {"name": "pvc-2", "namespace": "wire"}, "status": {"phase": "Pending"}},
    ]}
    target: PvcAllBound = PvcAllBound(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is False


def test_pvc_all_bound_collect_empty_returns_true() -> None:
    """PvcAllBound should return True when no PVCs exist."""
    data: dict[str, Any] = {"items": []}
    target: PvcAllBound = PvcAllBound(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: bool = target.collect()

    assert result is True


# ---------------------------------------------------------------------------
# EtcdHealth
# ---------------------------------------------------------------------------

def _make_node_with_ip(name: str, ip: str) -> dict[str, Any]:
    """Build a node object with an InternalIP address for EtcdHealth tests."""
    return {
        "metadata": {"name": name},
        "status": {
            "addresses": [
                {"type": "InternalIP", "address": ip},
                {"type": "Hostname", "address": name},
            ],
        },
    }


def test_etcd_health_description() -> None:
    """Check that EtcdHealth has the right description."""
    target: EtcdHealth = EtcdHealth(make_minimal_config(), _make_terminal(), _make_logger())
    assert "etcd" in target.description.lower()


def test_etcd_health_collect_healthy_etcdctl() -> None:
    """EtcdHealth should return 'healthy' when etcdctl reports healthy."""
    nodes_data: dict[str, Any] = {"items": [_make_node_with_ip("cp-1", "10.0.0.1")]}
    target: EtcdHealth = EtcdHealth(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), nodes_data)):
        with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(
            "127.0.0.1:2379 is healthy: successfully committed proposal"
        )):
            result: str = target.collect()

    assert result == "healthy"


def test_etcd_health_collect_healthy_curl_json() -> None:
    """EtcdHealth should return 'healthy' when curl /health reports true."""
    nodes_data: dict[str, Any] = {"items": [_make_node_with_ip("cp-1", "10.0.0.1")]}
    target: EtcdHealth = EtcdHealth(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), nodes_data)):
        with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(
            '{"health":"true"}'
        )):
            result: str = target.collect()

    assert result == "healthy"


def test_etcd_health_collect_unhealthy() -> None:
    """EtcdHealth should return 'unhealthy' when etcd is not responding."""
    nodes_data: dict[str, Any] = {"items": [_make_node_with_ip("cp-1", "10.0.0.1")]}
    target: EtcdHealth = EtcdHealth(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), nodes_data)):
        with patch("src.lib.ssh.SSHTarget.run", return_value=_ssh_cmd_result(
            "Error: context deadline exceeded"
        )):
            result: str = target.collect()

    assert result == "unhealthy"


def test_etcd_health_collect_no_nodes_raises() -> None:
    """EtcdHealth should raise when no nodes found in cluster."""
    nodes_data: dict[str, Any] = {"items": []}
    target: EtcdHealth = EtcdHealth(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), nodes_data)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_etcd_health_collect_null_data_raises() -> None:
    """EtcdHealth should raise when kubectl returns None."""
    target: EtcdHealth = EtcdHealth(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# IngressList
# ---------------------------------------------------------------------------

def test_ingress_list_description() -> None:
    """Check that IngressList has the right description."""
    target: IngressList = IngressList(make_minimal_config(), _make_terminal(), _make_logger())
    assert "Ingress" in target.description


def test_ingress_list_returns_entries() -> None:
    """IngressList returns formatted ingress entries."""
    data: dict[str, Any] = {"items": [
        {"metadata": {"name": "webapp", "namespace": "wire"},
         "spec": {"rules": [{"host": "webapp.example.com"}]}},
        {"metadata": {"name": "api", "namespace": "wire"},
         "spec": {"rules": [{"host": "nginz-https.example.com"}]}},
    ]}
    target: IngressList = IngressList(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: str = target.collect()

    assert "webapp.example.com" in result
    assert "nginz-https.example.com" in result


def test_ingress_list_empty_items() -> None:
    """IngressList should return empty string when no ingresses found."""
    data: dict[str, Any] = {"items": []}
    target: IngressList = IngressList(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), data)):
        result: str = target.collect()

    assert result == ""
    assert "No ingress" in target._health_info


def test_ingress_list_null_data_raises() -> None:
    """IngressList should raise when kubectl returns None."""
    target: IngressList = IngressList(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# KubernetesConfigmaps
# ---------------------------------------------------------------------------

def test_kubernetes_configmaps_description() -> None:
    """Check that KubernetesConfigmaps has the right description."""
    target: KubernetesConfigmaps = KubernetesConfigmaps(make_minimal_config(), _make_terminal(), _make_logger())
    assert "ConfigMap" in target.description


def test_kubernetes_configmaps_get_configmaps_returns_specs() -> None:
    """get_configmaps returns the expected list of specs."""
    target: KubernetesConfigmaps = KubernetesConfigmaps(make_minimal_config(), _make_terminal(), _make_logger())
    specs: list[dict[str, Any]] = target.get_configmaps()

    assert len(specs) > 0
    # Check known entries exist
    names: list[str] = [s["name"] for s in specs]
    assert "brig" in names
    assert "galley" in names
    assert "etcd" in names


def test_kubernetes_configmaps_collect_for_configmap_returns_content() -> None:
    """collect_for_configmap extracts the correct data key."""
    configmap_data: dict[str, Any] = {
        "data": {"brig.yaml": "host: brig.example.com\nport: 8080\n"},
    }
    spec: dict[str, Any] = {
        "name": "brig",
        "configmap_name": "brig",
        "namespace": None,
        "data_key": "brig.yaml",
        "description": "Brig config",
    }
    target: KubernetesConfigmaps = KubernetesConfigmaps(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), configmap_data)):
        result: str | None = target.collect_for_configmap(spec)

    assert result == "host: brig.example.com\nport: 8080\n"


def test_kubernetes_configmaps_collect_for_configmap_missing_key_raises() -> None:
    """Should raise when requested data key is not in the ConfigMap."""
    configmap_data: dict[str, Any] = {
        "data": {"other.yaml": "stuff"},
    }
    spec: dict[str, Any] = {
        "name": "brig",
        "configmap_name": "brig",
        "namespace": None,
        "data_key": "brig.yaml",
        "description": "Brig config",
    }
    target: KubernetesConfigmaps = KubernetesConfigmaps(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), configmap_data)):
        try:
            target.collect_for_configmap(spec)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_kubernetes_configmaps_collect_for_configmap_not_found_raises() -> None:
    """Should raise when ConfigMap doesn't exist (kubectl returns None)."""
    spec: dict[str, Any] = {
        "name": "brig",
        "configmap_name": "brig",
        "namespace": None,
        "data_key": "brig.yaml",
        "description": "Brig config",
    }
    target: KubernetesConfigmaps = KubernetesConfigmaps(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), None)):
        try:
            target.collect_for_configmap(spec)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_kubernetes_configmaps_collect_for_configmap_empty_data_raises() -> None:
    """Should raise when ConfigMap has no data section."""
    configmap_data: dict[str, Any] = {"data": {}}
    spec: dict[str, Any] = {
        "name": "brig",
        "configmap_name": "brig",
        "namespace": None,
        "data_key": "brig.yaml",
        "description": "Brig config",
    }
    target: KubernetesConfigmaps = KubernetesConfigmaps(make_minimal_config(), _make_terminal(), _make_logger())

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), configmap_data)):
        try:
            target.collect_for_configmap(spec)
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass
