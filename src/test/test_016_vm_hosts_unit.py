"""Unit tests for vm_hosts.

Tests discover_vm_hosts() mixes kubenodes from kubectl with database host
IPs from config, deduplicates by IP, and handles edge cases like empty kubectl
responses or nodes without InternalIP."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.lib.command import CommandResult
from src.lib.config import Config
from src.lib.vm_hosts import discover_vm_hosts
from src.test.conftest import make_minimal_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    cassandra: str = "10.0.0.10",
    elasticsearch: str = "10.0.0.11",
    minio: str = "10.0.0.12",
    postgresql: str = "10.0.0.13",
) -> Config:
    """Make a Config with custom DB IPs for testing.

    Uses make_minimal_config() to ensure all required fields exist, then
    overrides database IPs to whatever we need for the test.
    """
    base: Config = make_minimal_config()
    return replace(
        base,
        databases=replace(
            base.databases,
            cassandra=cassandra,
            elasticsearch=elasticsearch,
            minio=minio,
            postgresql=postgresql,
        ),
    )


def _cmd_result() -> CommandResult:
    """Build a fake CommandResult. discover_vm_hosts doesn't actually look at this."""
    return CommandResult(
        command="kubectl get nodes -o json",
        exit_code=0,
        stdout="{}",
        stderr="",
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )


def _make_node_item(name: str, internal_ip: str) -> dict[str, Any]:
    """Create a kubectl node item with name and InternalIP address."""
    return {
        "metadata": {"name": name},
        "status": {
            "addresses": [
                {"type": "InternalIP", "address": internal_ip},
                {"type": "Hostname", "address": name},
            ],
        },
    }


# ---------------------------------------------------------------------------
# discover_vm_hosts kubenodes only
# ---------------------------------------------------------------------------

def test_discover_vm_hosts_kubenodes_from_kubectl() -> None:
    """Check that kubenodes get pulled from kubectl get nodes."""
    config: Config = _make_config()
    kubectl_data: dict[str, Any] = {
        "items": [
            _make_node_item("kubenode1", "192.168.1.10"),
            _make_node_item("kubenode2", "192.168.1.11"),
        ],
    }

    def kubectl_fn(resource: str) -> tuple[CommandResult, dict[str, Any]]:
        return (_cmd_result(), kubectl_data)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # Should have 2 kubenodes + 4 datanodes (all distinct IPs)
    kube_hosts: list[dict[str, str]] = [h for h in hosts if h["name"].startswith("kubenode-")]
    assert len(kube_hosts) == 2
    assert kube_hosts[0] == {"name": "kubenode-192.168.1.10", "ip": "192.168.1.10"}
    assert kube_hosts[1] == {"name": "kubenode-192.168.1.11", "ip": "192.168.1.11"}


def test_discover_vm_hosts_datanodes_from_config() -> None:
    """Check that database IPs from config show up as datanodes."""
    config: Config = _make_config()

    # kubectl returns no nodes
    def kubectl_fn(resource: str) -> tuple[CommandResult, None]:
        return (_cmd_result(), None)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # All 4 DB IPs become datanodes
    assert len(hosts) == 4
    assert {"name": "datanode-10.0.0.10", "ip": "10.0.0.10"} in hosts
    assert {"name": "datanode-10.0.0.11", "ip": "10.0.0.11"} in hosts
    assert {"name": "datanode-10.0.0.12", "ip": "10.0.0.12"} in hosts
    assert {"name": "datanode-10.0.0.13", "ip": "10.0.0.13"} in hosts


# ---------------------------------------------------------------------------
# discover_vm_hosts deduplication
# ---------------------------------------------------------------------------

def test_discover_vm_hosts_deduplicates_by_ip() -> None:
    """Check that a host used as both kubenode and datanode only shows once."""
    # Cassandra IP matches a kubenode IP
    config: Config = _make_config(cassandra="192.168.1.10")
    kubectl_data: dict[str, Any] = {
        "items": [
            _make_node_item("kubenode1", "192.168.1.10"),
        ],
    }

    def kubectl_fn(resource: str) -> tuple[CommandResult, dict[str, Any]]:
        return (_cmd_result(), kubectl_data)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # kubenode-192.168.1.10 is already seen, so cassandra datanode is skipped
    ips: list[str] = [h["ip"] for h in hosts]
    assert ips.count("192.168.1.10") == 1
    # The kubenode-{ip} name should be used, not a datanode name
    matching: list[dict[str, str]] = [h for h in hosts if h["ip"] == "192.168.1.10"]
    assert matching[0]["name"] == "kubenode-192.168.1.10"


def test_discover_vm_hosts_deduplicates_among_db_ips() -> None:
    """Check that duplicate DB IPs get deduplicated when they're on the same host."""
    # All databases on the same IP
    config: Config = _make_config(
        cassandra="10.0.0.10",
        elasticsearch="10.0.0.10",
        minio="10.0.0.10",
        postgresql="10.0.0.10",
    )

    def kubectl_fn(resource: str) -> tuple[CommandResult, None]:
        return (_cmd_result(), None)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # Only one datanode entry for 10.0.0.10
    assert len(hosts) == 1
    assert hosts[0]["ip"] == "10.0.0.10"


# ---------------------------------------------------------------------------
# discover_vm_hosts kubectl returns None data
# ---------------------------------------------------------------------------

def test_discover_vm_hosts_kubectl_returns_none() -> None:
    """Check that we handle it cleanly when kubectl returns None."""
    config: Config = _make_config()

    def kubectl_fn(resource: str) -> tuple[CommandResult, None]:
        return (_cmd_result(), None)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # Only datanodes from config
    assert len(hosts) == 4
    assert all(h["name"].startswith("datanode-") for h in hosts)


# ---------------------------------------------------------------------------
# discover_vm_hosts empty items list
# ---------------------------------------------------------------------------

def test_discover_vm_hosts_empty_items() -> None:
    """Check that we handle an empty items list from kubectl."""
    config: Config = _make_config()
    kubectl_data: dict[str, Any] = {"items": []}

    def kubectl_fn(resource: str) -> tuple[CommandResult, dict[str, Any]]:
        return (_cmd_result(), kubectl_data)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # Only datanodes from config
    assert len(hosts) == 4


# ---------------------------------------------------------------------------
# discover_vm_hosts node without InternalIP
# ---------------------------------------------------------------------------

def test_discover_vm_hosts_skips_node_without_internal_ip() -> None:
    """Check that nodes without InternalIP get skipped."""
    config: Config = _make_config()
    kubectl_data: dict[str, Any] = {
        "items": [
            {
                "metadata": {"name": "node-no-ip"},
                "status": {
                    "addresses": [
                        {"type": "Hostname", "address": "node-no-ip"},
                    ],
                },
            },
            _make_node_item("kubenode1", "192.168.1.10"),
        ],
    }

    def kubectl_fn(resource: str) -> tuple[CommandResult, dict[str, Any]]:
        return (_cmd_result(), kubectl_data)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # node-no-ip should be skipped
    kube_names: list[str] = [h["name"] for h in hosts if h["name"].startswith("kubenode-")]
    assert "node-no-ip" not in kube_names
    assert "kubenode-192.168.1.10" in kube_names


def test_discover_vm_hosts_node_with_empty_addresses() -> None:
    """Check that nodes with empty addresses get skipped."""
    config: Config = _make_config()
    kubectl_data: dict[str, Any] = {
        "items": [
            {
                "metadata": {"name": "node-empty-addrs"},
                "status": {"addresses": []},
            },
        ],
    }

    def kubectl_fn(resource: str) -> tuple[CommandResult, dict[str, Any]]:
        return (_cmd_result(), kubectl_data)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    kube_names: list[str] = [h["name"] for h in hosts if h["name"].startswith("kubenode-")]
    assert len(kube_names) == 0


# ---------------------------------------------------------------------------
# discover_vm_hosts combined kubenodes + datanodes
# ---------------------------------------------------------------------------

def test_discover_vm_hosts_combined_output_order() -> None:
    """Check that kubenodes come first, then datanodes."""
    config: Config = _make_config()
    kubectl_data: dict[str, Any] = {
        "items": [
            _make_node_item("kubenode1", "192.168.1.10"),
            _make_node_item("kubenode2", "192.168.1.11"),
        ],
    }

    def kubectl_fn(resource: str) -> tuple[CommandResult, dict[str, Any]]:
        return (_cmd_result(), kubectl_data)

    hosts: list[dict[str, str]] = discover_vm_hosts(config, kubectl_fn)

    # First 2 should be kubenodes (kubenode-{ip}), then 4 datanodes (datanode-{ip})
    assert hosts[0]["name"] == "kubenode-192.168.1.10"
    assert hosts[1]["name"] == "kubenode-192.168.1.11"
    assert all(h["name"].startswith("datanode-") for h in hosts[2:])


def test_discover_vm_hosts_passes_correct_resource() -> None:
    """Check that kubectl_fn gets called with «nodes» as the resource."""
    config: Config = _make_config()
    called_with: list[str] = []

    def kubectl_fn(resource: str) -> tuple[CommandResult, None]:
        called_with.append(resource)
        return (_cmd_result(), None)

    discover_vm_hosts(config, kubectl_fn)

    assert called_with == ["nodes"]
