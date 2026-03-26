"""Shared test fixtures and helpers for all test modules.

We have one make_minimal_config() that every test uses, so when we add fields
to the Config dataclass, all tests automatically stay in sync. This prevents
the kind of test rot we hit with test_009 and test_018 after DatabasesConfig
and Config got new required fields.
"""

from __future__ import annotations

from src.lib.config import (
    AdminHostConfig,
    ClusterConfig,
    Config,
    DatabasesConfig,
    KubernetesConfig,
    NodesConfig,
    OptionsConfig,
)
from src.lib.wire_service_helpers import clear_pod_cache


def reset_test_caches() -> None:
    """Clear module-level caches so tests start with clean state.

    Called automatically by the test runner before each test.  Prevents
    stale pod data from one test leaking into the next via the
    wire_service_helpers module-level cache.
    """
    clear_pod_cache()


def make_minimal_config() -> Config:
    """Return a minimal but fully valid Config suitable for unit tests.

    Every required field gets a safe deterministic value, so targets can
    be instantiated without needing a real YAML file.

    Returns:
        A Config instance with every required field set.
    """
    return Config(
        admin_host=AdminHostConfig(
            ip="10.0.0.1",
            user="deploy",
            ssh_key="/tmp/test_key",
            ssh_port=22,
        ),
        cluster=ClusterConfig(
            domain="example.com",
            kubernetes_namespace="wire",
        ),
        databases=DatabasesConfig(
            cassandra="10.0.0.10",
            elasticsearch="10.0.0.11",
            minio="10.0.0.12",
            postgresql="10.0.0.13",
            rabbitmq="10.0.0.10",  # Co-located with Cassandra
            ssh_user="deploy",
            ssh_key="",
            ssh_port=22,
        ),
        kubernetes=KubernetesConfig(
            docker_image="",  # Empty means kubectl runs directly
            admin_home="/home/deploy",
            route_via_ssh=False,  # No SSH routing for kubectl in tests
        ),
        nodes=NodesConfig(
            kube_nodes=[],
            data_nodes=[],
        ),
        options=OptionsConfig(
            check_kubernetes=True,
            check_databases=True,
            check_network=True,
            check_wire_services=True,
            output_format="jsonl",
            output_file="results.jsonl",
        ),
        kubernetes_context="",
        wire_domain="example.com",
        timeout=30,
        raw={},
    )
