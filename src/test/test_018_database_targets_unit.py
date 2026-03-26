"""Unit tests for database target implementations.

Covers CassandraClusterStatus, CassandraNodeCount, ElasticsearchClusterHealth,
ElasticsearchNodeCount, MinioDrivesStatus, MinioNetworkStatus,
PostgresqlNodeCount, PostgresqlReplicationStatus, RabbitmqClusterStatus,
RabbitmqNodeCount, and RedisStatus.

Each target's collect() method is tested by mocking the underlying
run_db_command or kubectl_get functions that the target helpers delegate to.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from src.lib.base_target import BaseTarget
from src.lib.command import CommandResult
from src.lib.config import Config
from src.lib.logger import Logger, LogLevel
from src.lib.terminal import Terminal, Verbosity
from src.test.conftest import make_minimal_config
from src.targets.databases.cassandra.cluster_status import CassandraClusterStatus
from src.targets.databases.cassandra.node_count import CassandraNodeCount
from src.targets.databases.elasticsearch.cluster_health import ElasticsearchClusterHealth
from src.targets.databases.elasticsearch.node_count import ElasticsearchNodeCount
from src.targets.databases.minio.drives_status import MinioDrivesStatus
from src.targets.databases.minio.network_status import MinioNetworkStatus
from src.targets.databases.postgresql.node_count import PostgresqlNodeCount
from src.targets.databases.postgresql.replication_status import PostgresqlReplicationStatus
from src.targets.databases.rabbitmq.cluster_status import RabbitmqClusterStatus
from src.targets.databases.rabbitmq.node_count import RabbitmqNodeCount
from src.targets.databases.redis.status import RedisStatus
from src.targets.databases.cassandra.data_disk_usage import CassandraDataDiskUsage
from src.targets.databases.cassandra.keyspaces import CassandraKeyspaces
from src.targets.databases.cassandra.ntp_synchronized import CassandraNtpSynchronized
from src.targets.databases.cassandra.spar_idp_count import CassandraSparIdpCount
from src.targets.databases.cassandra.spar_tables import CassandraSparTables
from src.targets.databases.elasticsearch.read_only_check import ElasticsearchReadOnlyCheck
from src.targets.databases.elasticsearch.shard_count import ElasticsearchShardCount
from src.targets.databases.minio.bucket_count import MinioBucketCount
from src.targets.databases.minio.erasure_health import MinioErasureHealth
from src.targets.databases.minio.version import MinioVersion
from src.targets.databases.postgresql.replication_lag import PostgresqlReplicationLag
from src.targets.databases.postgresql.version import PostgresqlVersion
from src.targets.databases.rabbitmq.alarms import RabbitmqAlarms
from src.targets.databases.rabbitmq.queue_depth import RabbitmqQueueDepth
from src.targets.databases.rabbitmq.queue_persistence import RabbitmqQueuePersistence
from src.targets.databases.rabbitmq.version import RabbitmqVersion
from src.targets.databases.redis.memory import RedisMemory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Delegate to the single authoritative helper so field additions only need
# updating in one place (conftest.py), not in every test file.
_make_config = make_minimal_config


def _make_terminal() -> Terminal:
    """Create a quiet terminal so tests stay quiet."""
    return Terminal(verbosity=Verbosity.QUIET, use_color=False)


def _make_logger() -> Logger:
    """Create a logger that mutes everything."""
    return Logger(level=LogLevel.ERROR)


def _cmd_result(stdout: str, command: str = "test") -> CommandResult:
    """Make a successful CommandResult with given stdout."""
    return CommandResult(
        command=command,
        exit_code=0,
        stdout=stdout,
        stderr="",
        duration_seconds=0.01,
        success=True,
        timed_out=False,
    )


def _kubectl_cmd_result(stdout: str = "{}") -> CommandResult:
    """Make a successful CommandResult for kubectl output."""
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
# Cassandra CassandraClusterStatus
# ===========================================================================

def test_cassandra_cluster_status_description() -> None:
    """Check that CassandraClusterStatus has the right description."""
    target: CassandraClusterStatus = CassandraClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "All Cassandra nodes are Up/Normal"


def test_cassandra_cluster_status_all_un() -> None:
    """Make sure CassandraClusterStatus returns 'UN' when all the nodes are healthy."""
    nodetool_output: str = (
        "Datacenter: dc1\n"
        "===============\n"
        "Status=Up/Down\n"
        "|/ State=Normal/Leaving/Joining/Moving\n"
        "--  Address          Load       Tokens  Owns\n"
        "UN  192.168.122.10   125.3 GiB  256     33.3%\n"
        "UN  192.168.122.11   130.1 GiB  256     33.3%\n"
        "UN  192.168.122.12   128.5 GiB  256     33.3%\n"
    )
    target: CassandraClusterStatus = CassandraClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
        result: str = target.collect()

    assert result == "UN"


def test_cassandra_cluster_status_one_down() -> None:
    """Make sure CassandraClusterStatus returns first non-UN status if a node is down."""
    nodetool_output: str = (
        "Datacenter: dc1\n"
        "===============\n"
        "UN  192.168.122.10   125.3 GiB  256     33.3%\n"
        "DN  192.168.122.11   130.1 GiB  256     33.3%\n"
        "UN  192.168.122.12   128.5 GiB  256     33.3%\n"
    )
    target: CassandraClusterStatus = CassandraClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
        result: str = target.collect()

    assert result == "DN"


def test_cassandra_cluster_status_leaving_node() -> None:
    """Make sure CassandraClusterStatus detects UL (Up/Leaving) status."""
    nodetool_output: str = (
        "UN  192.168.122.10   125.3 GiB  256     50.0%\n"
        "UL  192.168.122.11   130.1 GiB  256     50.0%\n"
    )
    target: CassandraClusterStatus = CassandraClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
        result: str = target.collect()

    assert result == "UL"


def test_cassandra_cluster_status_no_nodes_raises() -> None:
    """Make sure CassandraClusterStatus raises when no node status lines found."""
    nodetool_output: str = "Datacenter: dc1\n===============\nNo data\n"
    target: CassandraClusterStatus = CassandraClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "no node status lines found" in str(err)


# ===========================================================================
# Cassandra CassandraNodeCount
# ===========================================================================

def test_cassandra_node_count_description() -> None:
    """Check that CassandraNodeCount has the right description."""
    target: CassandraNodeCount = CassandraNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Number of Cassandra nodes in the cluster"


def test_cassandra_node_count_unit() -> None:
    """Make sure CassandraNodeCount reports nodes unit."""
    target: CassandraNodeCount = CassandraNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.unit == "nodes"


def test_cassandra_node_count_three_nodes() -> None:
    """Make sure CassandraNodeCount counts 3 nodes from nodetool status."""
    nodetool_output: str = (
        "Datacenter: dc1\n"
        "===============\n"
        "UN  192.168.122.10   125.3 GiB  256     33.3%\n"
        "UN  192.168.122.11   130.1 GiB  256     33.3%\n"
        "DN  192.168.122.12   128.5 GiB  256     33.3%\n"
    )
    target: CassandraNodeCount = CassandraNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
        result: int = target.collect()

    assert result == 3


def test_cassandra_node_count_single_node() -> None:
    """Make sure CassandraNodeCount counts a single node."""
    nodetool_output: str = "UN  192.168.122.10   125.3 GiB  256     100.0%\n"
    target: CassandraNodeCount = CassandraNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
        result: int = target.collect()

    assert result == 1


def test_cassandra_node_count_no_nodes_raises() -> None:
    """Make sure CassandraNodeCount raises when no node lines parsed."""
    nodetool_output: str = "Datacenter: dc1\n===============\n"
    target: CassandraNodeCount = CassandraNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(nodetool_output)):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "no nodes found" in str(err)


# ===========================================================================
# Elasticsearch ElasticsearchClusterHealth
# ===========================================================================

def test_elasticsearch_cluster_health_description() -> None:
    """Check that ElasticsearchClusterHealth has the right description."""
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Elasticsearch cluster health status"


def test_elasticsearch_cluster_health_green() -> None:
    """Make sure ElasticsearchClusterHealth returns 'green' from JSON response."""
    json_output: str = '{"cluster_name":"wire","status":"green","number_of_nodes":3}'
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: str = target.collect()

    assert result == "green"


def test_elasticsearch_cluster_health_yellow() -> None:
    """Make sure ElasticsearchClusterHealth returns 'yellow' status."""
    json_output: str = '{"cluster_name":"wire","status":"yellow","number_of_nodes":2}'
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: str = target.collect()

    assert result == "yellow"


def test_elasticsearch_cluster_health_red() -> None:
    """Make sure ElasticsearchClusterHealth returns 'red' status."""
    json_output: str = '{"cluster_name":"wire","status":"red","number_of_nodes":1}'
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: str = target.collect()

    assert result == "red"


def test_elasticsearch_cluster_health_missing_status_field() -> None:
    """Make sure ElasticsearchClusterHealth returns 'unknown' if status field missing."""
    json_output: str = '{"cluster_name":"wire","number_of_nodes":3}'
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: str = target.collect()

    assert result == "unknown"


def test_elasticsearch_cluster_health_fallback_to_cat_health() -> None:
    """Make sure ElasticsearchClusterHealth falls back to _cat/health on JSON failure."""
    # First call returns invalid JSON, second call returns _cat/health text
    invalid_json: str = "not json at all"
    cat_output: str = "1735689600 12:00:00 wire green 3 3 15 15 0 0 0 0 - 100.0%"
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", side_effect=[
        _cmd_result(invalid_json),
        _cmd_result(cat_output),
    ]):
        result: str = target.collect()

    assert result == "green"


def test_elasticsearch_cluster_health_fallback_raises() -> None:
    """Make sure ElasticsearchClusterHealth raises when both methods fail."""
    invalid_json: str = "connection refused"
    empty_cat: str = ""
    target: ElasticsearchClusterHealth = ElasticsearchClusterHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", side_effect=[
            _cmd_result(invalid_json),
            _cmd_result(empty_cat),
        ]):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "Could not determine Elasticsearch cluster health" in str(err)


# ===========================================================================
# Elasticsearch ElasticsearchNodeCount
# ===========================================================================

def test_elasticsearch_node_count_description() -> None:
    """Check that ElasticsearchNodeCount has the right description."""
    target: ElasticsearchNodeCount = ElasticsearchNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Number of Elasticsearch nodes"


def test_elasticsearch_node_count_unit() -> None:
    """Make sure ElasticsearchNodeCount reports nodes unit."""
    target: ElasticsearchNodeCount = ElasticsearchNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.unit == "nodes"


def test_elasticsearch_node_count_from_json() -> None:
    """Make sure ElasticsearchNodeCount extracts count from JSON response."""
    json_output: str = '{"cluster_name":"wire","status":"green","number_of_nodes":3}'
    target: ElasticsearchNodeCount = ElasticsearchNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: int = target.collect()

    assert result == 3


def test_elasticsearch_node_count_missing_field_returns_zero() -> None:
    """Make sure ElasticsearchNodeCount returns 0 if number_of_nodes missing."""
    json_output: str = '{"cluster_name":"wire","status":"green"}'
    target: ElasticsearchNodeCount = ElasticsearchNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: int = target.collect()

    assert result == 0


def test_elasticsearch_node_count_fallback_to_cat_nodes() -> None:
    """Make sure ElasticsearchNodeCount falls back to counting _cat/nodes lines."""
    invalid_json: str = "not json"
    cat_output: str = "192.168.1.10 60 99 1 0.02 0.05 0.08 mdi * node1\n192.168.1.11 55 98 2 0.01 0.03 0.07 di - node2\n"
    target: ElasticsearchNodeCount = ElasticsearchNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", side_effect=[
        _cmd_result(invalid_json),
        _cmd_result(cat_output),
    ]):
        result: int = target.collect()

    assert result == 2


# ===========================================================================
# MinIO MinioDrivesStatus
# ===========================================================================

def test_minio_drives_status_description() -> None:
    """Check that MinioDrivesStatus has the right description."""
    target: MinioDrivesStatus = MinioDrivesStatus(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "MinIO drives health"


def test_minio_drives_status_online_offline_format() -> None:
    """Make sure MinioDrivesStatus parses 'X drives online, Y drives offline' format."""
    mc_output: str = (
        "  Status: 2 drives online, 0 drives offline\n"
        "  Total: 4 TiB\n"
    )
    target: MinioDrivesStatus = MinioDrivesStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "2/2 online"


def test_minio_drives_status_with_offline() -> None:
    """Make sure MinioDrivesStatus reports correct ratio when drives are offline."""
    mc_output: str = "  3 drives online, 1 drive offline\n"
    target: MinioDrivesStatus = MinioDrivesStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "3/4 online"


def test_minio_drives_status_newer_format() -> None:
    """Make sure MinioDrivesStatus parses 'Drives: X/Y OK' newer format."""
    mc_output: str = "  Drives: 4/4 OK\n  Pool: 1\n"
    target: MinioDrivesStatus = MinioDrivesStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "4/4 OK"


def test_minio_drives_status_raises_on_unparseable() -> None:
    """Make sure MinioDrivesStatus raises when output cannot be parsed."""
    mc_output: str = "Error: something went wrong\n"
    target: MinioDrivesStatus = MinioDrivesStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "Could not determine MinIO drives status" in str(err)


# ===========================================================================
# MinIO MinioNetworkStatus
# ===========================================================================

def test_minio_network_status_description() -> None:
    """Check that MinioNetworkStatus has the right description."""
    target: MinioNetworkStatus = MinioNetworkStatus(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "MinIO network health across all nodes"


def test_minio_network_status_from_json() -> None:
    """Make sure MinioNetworkStatus counts online peers from JSON output."""
    # Two servers, each reporting all peers online
    json_output: str = (
        '{"network":{"peer1":"online","peer2":"online"}}\n'
        '{"network":{"peer1":"online","peer2":"online"}}\n'
    )
    target: MinioNetworkStatus = MinioNetworkStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: str = target.collect()

    assert result == "4/4 OK"


def test_minio_network_status_some_offline() -> None:
    """Make sure MinioNetworkStatus counts offline peers correctly."""
    json_output: str = '{"network":{"peer1":"online","peer2":"offline"}}\n'
    target: MinioNetworkStatus = MinioNetworkStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: str = target.collect()

    assert result == "1/2 OK"


def test_minio_network_status_fallback_to_text() -> None:
    """Make sure MinioNetworkStatus falls back to text parsing when JSON has no network data."""
    # First call: JSON without network field
    json_output: str = '{"error":"something"}\n'
    # Second call: text output with Network pattern
    text_output: str = "  Network: 3/3 OK\n  Drives: 4/4 OK\n"
    target: MinioNetworkStatus = MinioNetworkStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", side_effect=[
        _cmd_result(json_output),
        _cmd_result(text_output),
    ]):
        result: str = target.collect()

    assert result == "3/3 OK"


def test_minio_network_status_raises_on_failure() -> None:
    """Make sure MinioNetworkStatus raises when both methods fail."""
    json_output: str = "not json"
    text_output: str = "Error: connection refused"
    target: MinioNetworkStatus = MinioNetworkStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", side_effect=[
            _cmd_result(json_output),
            _cmd_result(text_output),
        ]):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "Could not determine MinIO network status" in str(err)


# ===========================================================================
# PostgreSQL PostgresqlNodeCount
# ===========================================================================

def test_postgresql_node_count_description() -> None:
    """Check that PostgresqlNodeCount has the right description."""
    target: PostgresqlNodeCount = PostgresqlNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Number of PostgreSQL nodes"


def test_postgresql_node_count_unit() -> None:
    """Make sure PostgresqlNodeCount reports nodes unit."""
    target: PostgresqlNodeCount = PostgresqlNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.unit == "nodes"


def test_postgresql_node_count_three_nodes() -> None:
    """Make sure PostgresqlNodeCount counts nodes from repmgr cluster show output."""
    repmgr_output: str = (
        " ID | Name   | Role    | Status    | Upstream | Location | Priority | Timeline | Connection string\n"
        "----+--------+---------+-----------+----------+----------+----------+----------+------------------\n"
        " 1  | pg1    | primary | * running |          | default  | 100      | 1        | host=pg1\n"
        " 2  | pg2    | standby |   running | pg1      | default  | 100      | 1        | host=pg2\n"
        " 3  | pg3    | standby |   running | pg1      | default  | 100      | 1        | host=pg3\n"
    )
    target: PostgresqlNodeCount = PostgresqlNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
        result: int = target.collect()

    assert result == 3


def test_postgresql_node_count_no_data_raises() -> None:
    """Make sure PostgresqlNodeCount raises when no valid rows found."""
    repmgr_output: str = "ERROR: connection to database failed\n"
    target: PostgresqlNodeCount = PostgresqlNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "Could not parse repmgr" in str(err)


# ===========================================================================
# PostgreSQL PostgresqlReplicationStatus
# ===========================================================================

def test_postgresql_replication_status_description() -> None:
    """Check that PostgresqlReplicationStatus has the right description."""
    target: PostgresqlReplicationStatus = PostgresqlReplicationStatus(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "PostgreSQL repmgr cluster status"


def test_postgresql_replication_status_healthy() -> None:
    """Make sure PostgresqlReplicationStatus returns 'healthy' if all running."""
    repmgr_output: str = (
        " ID | Name   | Role    | Status    | Upstream | Location | Priority | Timeline | Connection string\n"
        "----+--------+---------+-----------+----------+----------+----------+----------+------------------\n"
        " 1  | pg1    | primary | * running |          | default  | 100      | 1        | host=pg1\n"
        " 2  | pg2    | standby |   running | pg1      | default  | 100      | 1        | host=pg2\n"
        " 3  | pg3    | standby |   running | pg1      | default  | 100      | 1        | host=pg3\n"
    )
    target: PostgresqlReplicationStatus = PostgresqlReplicationStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
        result: str = target.collect()

    assert result == "healthy"


def test_postgresql_replication_status_sets_dynamic_description() -> None:
    """Verify healthy status sets dynamic description with node counts."""
    repmgr_output: str = (
        " ID | Name | Role    | Status    | Upstream\n"
        "----+------+---------+-----------+----------\n"
        " 1  | pg1  | primary | * running |         \n"
        " 2  | pg2  | standby |   running | pg1     \n"
    )
    target: PostgresqlReplicationStatus = PostgresqlReplicationStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
        target.collect()

    assert "2-node" in target._dynamic_description
    assert "1 standbys" in target._dynamic_description


def test_postgresql_replication_status_degraded() -> None:
    """Make sure PostgresqlReplicationStatus returns 'degraded' if node not running."""
    repmgr_output: str = (
        " ID | Name | Role    | Status      | Upstream\n"
        "----+------+---------+-------------+----------\n"
        " 1  | pg1  | primary | * running   |         \n"
        " 2  | pg2  | standby |   stopped   | pg1     \n"
    )
    target: PostgresqlReplicationStatus = PostgresqlReplicationStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
        result: str = target.collect()

    assert result == "degraded"


def test_postgresql_replication_status_no_primary_degraded() -> None:
    """Make sure PostgresqlReplicationStatus returns 'degraded' if no primary found."""
    repmgr_output: str = (
        " ID | Name | Role    | Status    | Upstream\n"
        "----+------+---------+-----------+----------\n"
        " 2  | pg2  | standby |   running | pg1     \n"
        " 3  | pg3  | standby |   running | pg1     \n"
    )
    target: PostgresqlReplicationStatus = PostgresqlReplicationStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
        result: str = target.collect()

    assert result == "degraded"


def test_postgresql_replication_status_no_data_raises() -> None:
    """Make sure PostgresqlReplicationStatus raises when output is unparseable."""
    repmgr_output: str = "ERROR: connection to database failed\n"
    target: PostgresqlReplicationStatus = PostgresqlReplicationStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(repmgr_output)):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "Could not parse repmgr cluster show output" in str(err)


# ===========================================================================
# RabbitMQ RabbitmqClusterStatus
# ===========================================================================

def test_rabbitmq_cluster_status_description() -> None:
    """Check that RabbitmqClusterStatus has the right description."""
    target: RabbitmqClusterStatus = RabbitmqClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "RabbitMQ cluster status"


def test_rabbitmq_cluster_status_healthy() -> None:
    """Make sure RabbitmqClusterStatus returns 'healthy' if running with no alarms."""
    rabbitmq_output: str = (
        "Cluster status of node rabbit@node1 ...\n"
        "Basics\n"
        "\n"
        "Cluster name: rabbit@node1\n"
        "\n"
        "Running Nodes\n"
        "\n"
        "rabbit@node1\n"
        "rabbit@node2\n"
        "rabbit@node3\n"
        "\n"
        "Alarms\n"
        "\n"
        "(none)\n"
    )
    target: RabbitmqClusterStatus = RabbitmqClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
        result: str = target.collect()

    assert result == "healthy"


def test_rabbitmq_cluster_status_with_alarms() -> None:
    """Make sure RabbitmqClusterStatus returns 'alarms' if alarms are active."""
    # Alarm entries appear as plain text lines after the "Alarms" header;
    # "Node:" lines are treated as section headers and skipped by the parser
    rabbitmq_output: str = (
        "Running Nodes\n"
        "\n"
        "rabbit@node1\n"
        "\n"
        "Alarms\n"
        "\n"
        "memory_alarm\n"
    )
    target: RabbitmqClusterStatus = RabbitmqClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
        result: str = target.collect()

    assert result == "alarms"


def test_rabbitmq_cluster_status_unhealthy() -> None:
    """Make sure RabbitmqClusterStatus returns 'unhealthy' if no running nodes detected."""
    rabbitmq_output: str = "Error: unable to perform an operation on node rabbit@node1\n"
    target: RabbitmqClusterStatus = RabbitmqClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
        result: str = target.collect()

    assert result == "unhealthy"


def test_rabbitmq_cluster_status_running_nodes_lowercase() -> None:
    """Make sure RabbitmqClusterStatus detects running_nodes (Erlang format)."""
    rabbitmq_output: str = (
        "{running_nodes,[rabbit@node1,rabbit@node2]}\n"
        "{alarms,[]}\n"
    )
    target: RabbitmqClusterStatus = RabbitmqClusterStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
        result: str = target.collect()

    assert result == "healthy"


# ===========================================================================
# RabbitMQ RabbitmqNodeCount
# ===========================================================================

def test_rabbitmq_node_count_description() -> None:
    """Check that RabbitmqNodeCount has the right description."""
    target: RabbitmqNodeCount = RabbitmqNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Number of RabbitMQ nodes"


def test_rabbitmq_node_count_unit() -> None:
    """Make sure RabbitmqNodeCount reports nodes unit."""
    target: RabbitmqNodeCount = RabbitmqNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.unit == "nodes"


def test_rabbitmq_node_count_three_nodes() -> None:
    """Make sure RabbitmqNodeCount counts rabbit@ entries in Running Nodes section."""
    rabbitmq_output: str = (
        "Cluster status of node rabbit@node1 ...\n"
        "Running Nodes\n"
        "\n"
        "rabbit@node1\n"
        "rabbit@node2\n"
        "rabbit@node3\n"
        "\n"
        "Alarms\n"
    )
    target: RabbitmqNodeCount = RabbitmqNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
        result: int = target.collect()

    assert result == 3


def test_rabbitmq_node_count_single_node() -> None:
    """Make sure RabbitmqNodeCount counts a single node."""
    rabbitmq_output: str = (
        "Running Nodes\n"
        "\n"
        "rabbit@node1\n"
        "\n"
        "Disk Nodes\n"
    )
    target: RabbitmqNodeCount = RabbitmqNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
        result: int = target.collect()

    assert result == 1


def test_rabbitmq_node_count_no_nodes_raises() -> None:
    """Make sure RabbitmqNodeCount raises when no rabbit@ nodes found."""
    rabbitmq_output: str = "Error: unable to connect\n"
    target: RabbitmqNodeCount = RabbitmqNodeCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(rabbitmq_output)):
            target.collect()
        assert False, "Should\'ve raised RuntimeError"
    except RuntimeError as err:
        assert "Could not parse rabbitmqctl output" in str(err)


# ===========================================================================
# Redis RedisStatus
# ===========================================================================

def test_redis_status_description() -> None:
    """Check that RedisStatus has the right description."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Redis ephemeral master is running"


def test_redis_status_running() -> None:
    """Make sure RedisStatus returns 'running' if a Running pod is found."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    kubectl_data: dict[str, Any] = {
        "items": [
            {"status": {"phase": "Running"}},
        ],
    }

    with patch("src.lib.base_target.kubectl_get", return_value=(_cmd_result(""), kubectl_data)):
        result: str = target.collect()

    assert result == "running"


def test_redis_status_not_running() -> None:
    """Make sure RedisStatus returns 'not running' if no Running pod found."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    kubectl_data: dict[str, Any] = {
        "items": [
            {"status": {"phase": "Pending"}},
        ],
    }

    with patch("src.lib.base_target.kubectl_get", return_value=(_cmd_result(""), kubectl_data)):
        result: str = target.collect()

    assert result == "not running"


def test_redis_status_empty_pods() -> None:
    """Make sure RedisStatus returns 'not running' if no pods found."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    kubectl_data: dict[str, Any] = {"items": []}

    with patch("src.lib.base_target.kubectl_get", return_value=(_cmd_result(""), kubectl_data)):
        result: str = target.collect()

    assert result == "not running"


def test_redis_status_fallback_label() -> None:
    """Verify RedisStatus tries alternative label when first selector returns None."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    # First kubectl call returns None data (preferred label not found)
    # Second kubectl call returns a running pod (fallback label)
    fallback_data: dict[str, Any] = {
        "items": [
            {"status": {"phase": "Running"}},
        ],
    }

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_cmd_result(""), None),
        (_cmd_result(""), fallback_data),
    ]):
        result: str = target.collect()

    assert result == "running"


def test_redis_status_both_labels_fail_raises() -> None:
    """Make sure RedisStatus raises when both label selectors return None data."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_cmd_result(""), None),
        (_cmd_result(""), None),
    ]):
        try:
            target.collect()
            assert False, "Should\'ve raised RuntimeError"
        except RuntimeError as err:
            assert "Could not find Redis pods" in str(err)


def test_redis_status_pod_without_phase() -> None:
    """Verify RedisStatus handles pods with missing phase gracefully."""
    target: RedisStatus = RedisStatus(
        _make_config(), _make_terminal(), _make_logger()
    )

    kubectl_data: dict[str, Any] = {
        "items": [
            {"status": {}},
            {"status": {"phase": "Running"}},
        ],
    }

    with patch("src.lib.base_target.kubectl_get", return_value=(_cmd_result(""), kubectl_data)):
        result: str = target.collect()

    assert result == "running"


# ===========================================================================
# Cassandra CassandraDataDiskUsage
# ===========================================================================

def test_cassandra_data_disk_usage_description() -> None:
    """Check that CassandraDataDiskUsage has the right description."""
    target: CassandraDataDiskUsage = CassandraDataDiskUsage(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Cassandra data directory disk usage"


def test_cassandra_data_disk_usage_normal() -> None:
    """Make sure CassandraDataDiskUsage returns usage percentage from df output."""
    df_output: str = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/sda2       100G   45G   55G  45% /mnt/cassandra/data\n"
    )
    target: CassandraDataDiskUsage = CassandraDataDiskUsage(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(df_output)):
        result: int = target.collect()

    assert result == 45
    assert "45%" in target._health_info


def test_cassandra_data_disk_usage_critical() -> None:
    """Verify CassandraDataDiskUsage flags critical usage at 90%+."""
    df_output: str = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/sda2       100G   92G    8G  92% /mnt/cassandra/data\n"
    )
    target: CassandraDataDiskUsage = CassandraDataDiskUsage(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(df_output)):
        result: int = target.collect()

    assert result == 92
    assert "CRITICAL" in target._health_info


def test_cassandra_data_disk_usage_warning() -> None:
    """Verify CassandraDataDiskUsage flags warning usage at 75-89%."""
    df_output: str = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/sda2       100G   80G   20G  80% /mnt/cassandra/data\n"
    )
    target: CassandraDataDiskUsage = CassandraDataDiskUsage(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(df_output)):
        result: int = target.collect()

    assert result == 80
    assert "WARNING" in target._health_info


def test_cassandra_data_disk_usage_too_few_lines_raises() -> None:
    """Make sure CassandraDataDiskUsage raises on insufficient df output."""
    target: CassandraDataDiskUsage = CassandraDataDiskUsage(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# Cassandra CassandraKeyspaces
# ===========================================================================

def test_cassandra_keyspaces_description() -> None:
    """Check that CassandraKeyspaces has the right description."""
    target: CassandraKeyspaces = CassandraKeyspaces(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "Required Cassandra keyspaces present"


def test_cassandra_keyspaces_all_present_via_cqlsh() -> None:
    """Make sure CassandraKeyspaces returns True if all required keyspaces exist via cqlsh."""
    cqlsh_output: str = "system_schema  system  brig  galley  spar  gundeck  system_auth"
    target: CassandraKeyspaces = CassandraKeyspaces(
        _make_config(), _make_terminal(), _make_logger()
    )

    # CQL fails, cqlsh succeeds
    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result(cqlsh_output)):
            result: bool = target.collect()

    assert result is True


def test_cassandra_keyspaces_missing_galley() -> None:
    """Make sure CassandraKeyspaces returns False if a required keyspace is missing."""
    cqlsh_output: str = "system_schema  brig  spar  gundeck"
    target: CassandraKeyspaces = CassandraKeyspaces(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result(cqlsh_output)):
            result: bool = target.collect()

    assert result is False
    assert "galley" in target._health_info


def test_cassandra_keyspaces_both_methods_fail_raises() -> None:
    """Make sure CassandraKeyspaces raises when both CQL and cqlsh fail."""
    target: CassandraKeyspaces = CassandraKeyspaces(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result("")):
            try:
                target.collect()
                assert False, "Expected RuntimeError"
            except RuntimeError:
                pass


# ===========================================================================
# Cassandra CassandraNtpSynchronized
# ===========================================================================

def test_cassandra_ntp_synchronized_description() -> None:
    """Check that CassandraNtpSynchronized has the right description."""
    target: CassandraNtpSynchronized = CassandraNtpSynchronized(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "NTP" in target.description


def test_cassandra_ntp_synchronized_yes() -> None:
    """Verify returns True when timedatectl reports NTPSynchronized=yes."""
    target: CassandraNtpSynchronized = CassandraNtpSynchronized(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("NTPSynchronized=yes\nNTP=yes\n")):
        result: bool = target.collect()

    assert result is True


def test_cassandra_ntp_synchronized_no() -> None:
    """Verify returns False when timedatectl reports NTPSynchronized=no."""
    target: CassandraNtpSynchronized = CassandraNtpSynchronized(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("NTPSynchronized=no\nNTP=no\n")):
        result: bool = target.collect()

    assert result is False


def test_cassandra_ntp_synchronized_human_readable() -> None:
    """Verify parses human-readable timedatectl format with 'synchronized: yes'."""
    target: CassandraNtpSynchronized = CassandraNtpSynchronized(
        _make_config(), _make_terminal(), _make_logger()
    )
    human_output: str = (
        "               Local time: Thu 2026-03-14 12:00:00 UTC\n"
        " System clock synchronized: yes\n"
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(human_output)):
        result: bool = target.collect()

    assert result is True


def test_cassandra_ntp_synchronized_unknown_output() -> None:
    """Verify returns False when timedatectl output is unparseable."""
    target: CassandraNtpSynchronized = CassandraNtpSynchronized(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("some random output\n")):
        result: bool = target.collect()

    assert result is False


# ===========================================================================
# Cassandra CassandraSparIdpCount
# ===========================================================================

def test_cassandra_spar_idp_count_description() -> None:
    """Check that CassandraSparIdpCount has the right description."""
    target: CassandraSparIdpCount = CassandraSparIdpCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "spar" in target.description.lower()


def test_cassandra_spar_idp_count_via_cqlsh() -> None:
    """Verify returns count from cqlsh output when CQL fails."""
    cqlsh_output: str = "\n count\n-------\n     3\n\n(1 rows)\n"
    target: CassandraSparIdpCount = CassandraSparIdpCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result(cqlsh_output)):
            result: int = target.collect()

    assert result == 3


def test_cassandra_spar_idp_count_zero() -> None:
    """Verify returns 0 and notes no IdPs when count is zero."""
    cqlsh_output: str = "\n count\n-------\n     0\n\n(1 rows)\n"
    target: CassandraSparIdpCount = CassandraSparIdpCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result(cqlsh_output)):
            result: int = target.collect()

    assert result == 0
    assert "No SAML IdPs" in target._health_info


def test_cassandra_spar_idp_count_both_fail_raises() -> None:
    """Verify raises when both CQL and cqlsh fail to return count."""
    target: CassandraSparIdpCount = CassandraSparIdpCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result("")):
            try:
                target.collect()
                assert False, "Expected RuntimeError"
            except RuntimeError:
                pass


# ===========================================================================
# Cassandra CassandraSparTables
# ===========================================================================

def test_cassandra_spar_tables_description() -> None:
    """Check that CassandraSparTables has the right description."""
    target: CassandraSparTables = CassandraSparTables(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "spar" in target.description.lower()


def test_cassandra_spar_tables_all_present_via_cqlsh() -> None:
    """Verify returns True when all required spar tables exist."""
    cqlsh_output: str = (
        " table_name\n"
        "------------\n"
        "        idp\n"
        " issuer_idp\n"
        "       user\n"
        "       bind\n"
        " auth_token\n"
    )
    target: CassandraSparTables = CassandraSparTables(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result(cqlsh_output)):
            result: bool = target.collect()

    assert result is True


def test_cassandra_spar_tables_missing_bind() -> None:
    """Verify returns False when a required spar table is missing."""
    cqlsh_output: str = (
        " table_name\n"
        "------------\n"
        "        idp\n"
        " issuer_idp\n"
        "       user\n"
    )
    target: CassandraSparTables = CassandraSparTables(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result(cqlsh_output)):
            result: bool = target.collect()

    assert result is False
    assert "bind" in target._health_info


def test_cassandra_spar_tables_both_fail_raises() -> None:
    """Verify raises when both CQL and cqlsh fail."""
    target: CassandraSparTables = CassandraSparTables(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_cql_query", side_effect=Exception("No CQL")):
        with patch.object(BaseTarget, "run_cqlsh", return_value=_cmd_result("")):
            try:
                target.collect()
                assert False, "Expected RuntimeError"
            except RuntimeError:
                pass


# ===========================================================================
# Elasticsearch ElasticsearchReadOnlyCheck
# ===========================================================================

def test_elasticsearch_read_only_check_description() -> None:
    """Check that ElasticsearchReadOnlyCheck has the right description."""
    target: ElasticsearchReadOnlyCheck = ElasticsearchReadOnlyCheck(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "read-only" in target.description.lower()


def test_elasticsearch_read_only_check_no_blocked_indices() -> None:
    """Verify returns True when no indices have read_only_allow_delete."""
    settings_json: str = (
        '{"wire-brig":{"settings":{"index.blocks.read_only_allow_delete":"false"}},'
        '"wire-galley":{"settings":{"index.number_of_replicas":"1"}}}'
    )
    target: ElasticsearchReadOnlyCheck = ElasticsearchReadOnlyCheck(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(settings_json)):
        result: bool = target.collect()

    assert result is True


def test_elasticsearch_read_only_check_blocked_index() -> None:
    """Verify returns False when an index has read_only_allow_delete=true."""
    settings_json: str = (
        '{"wire-brig":{"settings":{"index.blocks.read_only_allow_delete":"true"}},'
        '"wire-galley":{"settings":{"index.number_of_replicas":"1"}}}'
    )
    target: ElasticsearchReadOnlyCheck = ElasticsearchReadOnlyCheck(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(settings_json)):
        result: bool = target.collect()

    assert result is False
    assert "wire-brig" in target._health_info


def test_elasticsearch_read_only_check_invalid_json_raises() -> None:
    """Verify raises when settings endpoint returns invalid JSON."""
    target: ElasticsearchReadOnlyCheck = ElasticsearchReadOnlyCheck(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("not json")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# Elasticsearch ElasticsearchShardCount
# ===========================================================================

def test_elasticsearch_shard_count_description() -> None:
    """Check that ElasticsearchShardCount has the right description."""
    target: ElasticsearchShardCount = ElasticsearchShardCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "shard" in target.description.lower()


def test_elasticsearch_shard_count_all_assigned() -> None:
    """Verify returns active_shards count when all are assigned."""
    health_json: str = '{"active_shards":30,"unassigned_shards":0,"relocating_shards":0}'
    target: ElasticsearchShardCount = ElasticsearchShardCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(health_json)):
        result: int = target.collect()

    assert result == 30
    assert "all assigned" in target._health_info


def test_elasticsearch_shard_count_unassigned() -> None:
    """Verify health info notes unassigned shards."""
    health_json: str = '{"active_shards":28,"unassigned_shards":2,"relocating_shards":0}'
    target: ElasticsearchShardCount = ElasticsearchShardCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(health_json)):
        result: int = target.collect()

    assert result == 28
    assert "2 unassigned" in target._health_info


def test_elasticsearch_shard_count_invalid_json_raises() -> None:
    """Verify raises when health API returns invalid JSON."""
    target: ElasticsearchShardCount = ElasticsearchShardCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("connection refused")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# MinIO MinioBucketCount
# ===========================================================================

def test_minio_bucket_count_description() -> None:
    """Check that MinioBucketCount has the right description."""
    target: MinioBucketCount = MinioBucketCount(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "MinIO bucket count"


def test_minio_bucket_count_from_json() -> None:
    """Verify parses bucket count from JSON output."""
    json_output: str = '{"info":{"buckets":{"count":5}}}'
    target: MinioBucketCount = MinioBucketCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(json_output)):
        result: int = target.collect()

    assert result == 5


def test_minio_bucket_count_from_text() -> None:
    """Verify parses bucket count from 'X Buckets' text pattern."""
    text_output: str = "  3 Buckets, 10 Objects\n  Total: 2 GiB\n"
    target: MinioBucketCount = MinioBucketCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(text_output)):
        result: int = target.collect()

    assert result == 3


def test_minio_bucket_count_unparseable_raises() -> None:
    """Verify raises when output cannot be parsed."""
    target: MinioBucketCount = MinioBucketCount(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("Error: connection refused")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# MinIO MinioErasureHealth
# ===========================================================================

def test_minio_erasure_health_description() -> None:
    """Check that MinioErasureHealth has the right description."""
    target: MinioErasureHealth = MinioErasureHealth(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "erasure" in target.description.lower()


def test_minio_erasure_health_read_write() -> None:
    """Verify returns 'read-write' when all drives are online."""
    mc_output: str = "  2 drives online, 0 drives offline\n  Mode: read-write\n"
    target: MinioErasureHealth = MinioErasureHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "read-write"


def test_minio_erasure_health_degraded() -> None:
    """Verify returns 'degraded' when some drives are offline."""
    mc_output: str = "  3 drives online, 1 drive offline\n  Mode: online\n"
    target: MinioErasureHealth = MinioErasureHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "degraded"


def test_minio_erasure_health_read_only() -> None:
    """Verify returns 'read-only' when cluster is in read-only mode."""
    mc_output: str = "  Status: read-only\n  Quorum lost, cannot write\n"
    target: MinioErasureHealth = MinioErasureHealth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "read-only"


# ===========================================================================
# MinIO MinioVersion
# ===========================================================================

def test_minio_version_description() -> None:
    """Check that MinioVersion has the right description."""
    target: MinioVersion = MinioVersion(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "MinIO server version"


def test_minio_version_release_format() -> None:
    """Verify parses RELEASE.xxx version format."""
    mc_output: str = "  Version: RELEASE.2023-07-21T21-12-44Z\n  Network: 2/2 OK\n"
    target: MinioVersion = MinioVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "RELEASE.2023-07-21T21-12-44Z"


def test_minio_version_version_prefix_format() -> None:
    """Verify parses 'Version: X.Y.Z' format."""
    mc_output: str = "Version: 2024.1.29\nDrives: 4/4 OK\n"
    target: MinioVersion = MinioVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(mc_output)):
        result: str = target.collect()

    assert result == "2024.1.29"


def test_minio_version_empty_raises() -> None:
    """Verify raises when output is empty."""
    target: MinioVersion = MinioVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# PostgreSQL PostgresqlReplicationLag
# ===========================================================================

def test_postgresql_replication_lag_description() -> None:
    """Check that PostgresqlReplicationLag has the right description."""
    target: PostgresqlReplicationLag = PostgresqlReplicationLag(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "replication lag" in target.description.lower()


def test_postgresql_replication_lag_no_lag() -> None:
    """Verify returns summary when standbys have no lag."""
    psql_output: str = " pg2       | 00:00:00.003795 | streaming\n"
    target: PostgresqlReplicationLag = PostgresqlReplicationLag(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(psql_output)):
        result: str = target.collect()

    assert "pg2" in result
    assert "No significant lag" in target._health_info


def test_postgresql_replication_lag_high_lag() -> None:
    """Verify flags replication lag above 1 second."""
    psql_output: str = " pg2       | 00:01:30.5 | streaming\n"
    target: PostgresqlReplicationLag = PostgresqlReplicationLag(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(psql_output)):
        result: str = target.collect()

    assert "Replication lag detected" in target._health_info


def test_postgresql_replication_lag_no_replication() -> None:
    """Verify returns 'no replication' when empty output and not a standby."""
    target: PostgresqlReplicationLag = PostgresqlReplicationLag(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", side_effect=[
        _cmd_result(""),       # pg_stat_replication empty
        _cmd_result(" f\n"),   # not in recovery (is primary)
    ]):
        result: str = target.collect()

    assert "no replication" in result.lower()


def test_postgresql_replication_lag_standby_node() -> None:
    """Verify returns standby message when node is a standby."""
    target: PostgresqlReplicationLag = PostgresqlReplicationLag(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", side_effect=[
        _cmd_result("(0 rows)"),   # no replication data
        _cmd_result(" t\n"),       # pg_is_in_recovery = true
    ]):
        result: str = target.collect()

    assert "standby" in result.lower()


def test_postgresql_replication_lag_parse_interval() -> None:
    """Verify _parse_pg_interval_seconds correctly converts intervals."""
    assert PostgresqlReplicationLag._parse_pg_interval_seconds("00:00:00") == 0.0
    assert PostgresqlReplicationLag._parse_pg_interval_seconds("00:01:30.5") == 90.5
    assert PostgresqlReplicationLag._parse_pg_interval_seconds("01:00:00") == 3600.0
    assert PostgresqlReplicationLag._parse_pg_interval_seconds("") == 0.0
    assert PostgresqlReplicationLag._parse_pg_interval_seconds("bad") == 0.0


# ===========================================================================
# PostgreSQL PostgresqlVersion
# ===========================================================================

def test_postgresql_version_description() -> None:
    """Check that PostgresqlVersion has the right description."""
    target: PostgresqlVersion = PostgresqlVersion(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "PostgreSQL version"


def test_postgresql_version_from_select_version() -> None:
    """Verify parses version from SELECT version() output."""
    psql_output: str = "PostgreSQL 15.4 (Ubuntu 15.4-1.pgdg22.04+1) on x86_64-linux-gnu\n"
    target: PostgresqlVersion = PostgresqlVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(psql_output)):
        result: str = target.collect()

    assert "PostgreSQL 15.4" in result


def test_postgresql_version_empty_raises() -> None:
    """Verify raises when output is empty."""
    target: PostgresqlVersion = PostgresqlVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# RabbitMQ RabbitmqAlarms
# ===========================================================================

def test_rabbitmq_alarms_description() -> None:
    """Check that RabbitmqAlarms has the right description."""
    target: RabbitmqAlarms = RabbitmqAlarms(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "alarm" in target.description.lower()


def test_rabbitmq_alarms_no_alarms() -> None:
    """Verify returns True when no alarms are active."""
    status_output: str = (
        "Status of node rabbit@node1 ...\n"
        "Uptime: 3600\n"
        "PID: 1234\n"
    )
    target: RabbitmqAlarms = RabbitmqAlarms(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(status_output)):
        result: bool = target.collect()

    assert result is True


def test_rabbitmq_alarms_memory_alarm() -> None:
    """Verify returns False when memory alarm is active."""
    status_output: str = (
        "Alarms\n"
        "memory_alarm: triggered\n"
    )
    target: RabbitmqAlarms = RabbitmqAlarms(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(status_output)):
        result: bool = target.collect()

    assert result is False


def test_rabbitmq_alarms_resource_alarm_erlang() -> None:
    """Verify detects Erlang-style resource_alarm entries."""
    status_output: str = "{resource_alarm,disk}\n{running,true}\n"
    target: RabbitmqAlarms = RabbitmqAlarms(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(status_output)):
        result: bool = target.collect()

    assert result is False


# ===========================================================================
# RabbitMQ RabbitmqQueueDepth
# ===========================================================================

def test_rabbitmq_queue_depth_description() -> None:
    """Check that RabbitmqQueueDepth has the right description."""
    target: RabbitmqQueueDepth = RabbitmqQueueDepth(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "queue" in target.description.lower()


def test_rabbitmq_queue_depth_normal() -> None:
    """Verify returns max depth when all queues are within threshold."""
    list_output: str = (
        "Listing queues for vhost / ...\n"
        "brig-events\t50\n"
        "galley-events\t10\n"
        "gundeck-events\t200\n"
    )
    target: RabbitmqQueueDepth = RabbitmqQueueDepth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(list_output)):
        result: int = target.collect()

    assert result == 200
    assert "3 queues" in target._health_info


def test_rabbitmq_queue_depth_backlog() -> None:
    """Verify flags queues above 1000 message threshold."""
    list_output: str = (
        "brig-events\t5000\n"
        "galley-events\t10\n"
    )
    target: RabbitmqQueueDepth = RabbitmqQueueDepth(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(list_output)):
        result: int = target.collect()

    assert result == 5000
    assert "brig-events" in target._health_info


def test_rabbitmq_queue_depth_empty_raises() -> None:
    """Verify raises when list_queues returns no output."""
    target: RabbitmqQueueDepth = RabbitmqQueueDepth(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# RabbitMQ RabbitmqQueuePersistence
# ===========================================================================

def test_rabbitmq_queue_persistence_description() -> None:
    """Check that RabbitmqQueuePersistence has the right description."""
    target: RabbitmqQueuePersistence = RabbitmqQueuePersistence(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "durable" in target.description.lower()


def test_rabbitmq_queue_persistence_all_durable() -> None:
    """Verify returns 0 when all queues are durable."""
    list_output: str = (
        "Listing queues for vhost / ...\n"
        "brig-events\ttrue\n"
        "galley-events\ttrue\n"
    )
    target: RabbitmqQueuePersistence = RabbitmqQueuePersistence(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(list_output)):
        result: int = target.collect()

    assert result == 0
    assert "All 2 queue(s) are durable" in target._health_info


def test_rabbitmq_queue_persistence_one_not_durable() -> None:
    """Verify returns count of non-durable queues."""
    list_output: str = (
        "Listing queues for vhost / ...\n"
        "brig-events\ttrue\n"
        "temp-queue\tfalse\n"
    )
    target: RabbitmqQueuePersistence = RabbitmqQueuePersistence(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(list_output)):
        result: int = target.collect()

    assert result == 1
    assert "temp-queue" in target._health_info


def test_rabbitmq_queue_persistence_empty_raises() -> None:
    """Verify raises when list_queues returns no output."""
    target: RabbitmqQueuePersistence = RabbitmqQueuePersistence(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# RabbitMQ RabbitmqVersion
# ===========================================================================

def test_rabbitmq_version_description() -> None:
    """Check that RabbitmqVersion has the right description."""
    target: RabbitmqVersion = RabbitmqVersion(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert target.description == "RabbitMQ version"


def test_rabbitmq_version_standard_format() -> None:
    """Verify parses 'RabbitMQ 3.x.y' format."""
    output: str = (
        "Cluster status of node rabbit@node1\n"
        "Versions\n"
        "RabbitMQ 3.9.27 on Erlang 25.3\n"
    )
    target: RabbitmqVersion = RabbitmqVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(output)):
        result: str = target.collect()

    assert result == "3.9.27"


def test_rabbitmq_version_erlang_format() -> None:
    """Verify parses Erlang-tuple version format."""
    output: str = '{rabbit, 3.12.0}\n'
    target: RabbitmqVersion = RabbitmqVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(output)):
        result: str = target.collect()

    assert result == "3.12.0"


def test_rabbitmq_version_bare_number() -> None:
    """Verify parses bare version number from 'rabbitmqctl version'."""
    output: str = "3.13.1\n"
    target: RabbitmqVersion = RabbitmqVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result(output)):
        result: str = target.collect()

    assert result == "3.13.1"


def test_rabbitmq_version_unparseable_raises() -> None:
    """Verify raises when version cannot be determined."""
    target: RabbitmqVersion = RabbitmqVersion(
        _make_config(), _make_terminal(), _make_logger()
    )

    try:
        with patch.object(BaseTarget, "run_db_command", return_value=_cmd_result("Error: unable to connect")):
            target.collect()
        assert False, "Expected RuntimeError"
    except RuntimeError:
        pass


# ===========================================================================
# Redis RedisMemory
# ===========================================================================

def test_redis_memory_description() -> None:
    """Check that RedisMemory has the right description."""
    target: RedisMemory = RedisMemory(
        _make_config(), _make_terminal(), _make_logger()
    )
    assert "memory" in target.description.lower()


def test_redis_memory_healthy() -> None:
    """Verify returns summary with zero evicted keys."""
    redis_info: str = (
        "# Memory\n"
        "used_memory_human:10.50M\n"
        "maxmemory_human:256.00M\n"
        "evicted_keys:0\n"
    )
    pods_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "redis-master-0", "namespace": "wire"}, "status": {"phase": "Running"}},
    ]}
    target: RedisMemory = RedisMemory(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), pods_data)):
        with patch("src.lib.base_target.kubectl_raw", return_value=_cmd_result(redis_info)):
            result: str = target.collect()

    assert "used=10.50M" in result
    assert "evicted=0" in result


def test_redis_memory_evicting() -> None:
    """Verify flags evicted keys in health info."""
    redis_info: str = (
        "# Memory\n"
        "used_memory_human:250.00M\n"
        "maxmemory_human:256.00M\n"
        "evicted_keys:1523\n"
    )
    pods_data: dict[str, Any] = {"items": [
        {"metadata": {"name": "redis-master-0", "namespace": "wire"}, "status": {"phase": "Running"}},
    ]}
    target: RedisMemory = RedisMemory(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch("src.lib.base_target.kubectl_get", return_value=(_kubectl_cmd_result(), pods_data)):
        with patch("src.lib.base_target.kubectl_raw", return_value=_cmd_result(redis_info)):
            result: str = target.collect()

    assert "evicted=1523" in result
    assert "WARNING" in target._health_info


def test_redis_memory_no_pods_raises() -> None:
    """Verify raises when no Redis pods are found."""
    empty: dict[str, Any] = {"items": []}
    target: RedisMemory = RedisMemory(
        _make_config(), _make_terminal(), _make_logger()
    )

    with patch("src.lib.base_target.kubectl_get", side_effect=[
        (_kubectl_cmd_result(), empty),
        (_kubectl_cmd_result(), empty),
        (_kubectl_cmd_result(), empty),
    ]):
        try:
            target.collect()
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass
