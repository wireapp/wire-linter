"""Unit tests for the configuration loader and validator module.

Covers IPv4 validation, ConfigError formatting, load_config with
valid data, error collection, missing file handling, YAML parse errors,
explicit overrides, non-integer ssh_port, and options defaults.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

from src.lib.config import is_valid_ipv4, ConfigError, load_config, Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp_yaml(content: str) -> str:
    """Write content to a temporary .yaml file and return its path.

    Args:
        content: YAML string to write.

    Returns:
        Absolute path to the temporary file. Caller must delete it.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


def _make_valid_yaml(ssh_key_path: str) -> str:
    """Build a minimal valid config YAML string.

    Args:
        ssh_key_path: Absolute path to an existing SSH key file.

    Returns:
        A YAML string with all required fields populated.
    """
    return (
        "admin_host:\n"
        "  ip: 10.0.0.1\n"
        "  user: deploy\n"
        f'  ssh_key: "{ssh_key_path}"\n'
        "  ssh_port: 22\n"
        "cluster:\n"
        "  domain: wire.example.com\n"
        "  kubernetes_namespace: wire-prod\n"
        "databases:\n"
        "  cassandra: 10.0.1.1\n"
        "  elasticsearch: 10.0.1.2\n"
        "  minio: 10.0.1.3\n"
        "  postgresql: 10.0.1.4\n"
    )


# ---------------------------------------------------------------------------
# is_valid_ipv4
# ---------------------------------------------------------------------------

def test_is_valid_ipv4_valid() -> None:
    """Valid IPv4 addresses accepted."""
    assert is_valid_ipv4("192.168.1.1") is True, "Standard private IP"
    assert is_valid_ipv4("10.0.0.1") is True, "10.x range"
    assert is_valid_ipv4("0.0.0.0") is True, "All zeros"
    assert is_valid_ipv4("255.255.255.255") is True, "All 255s"
    assert is_valid_ipv4("1.1.1.1") is True, "Single digit octets"


def test_is_valid_ipv4_invalid() -> None:
    """Invalid IPv4 addresses rejected."""
    assert is_valid_ipv4("256.1.1.1") is False, "Octet > 255"
    assert is_valid_ipv4("1.2.3") is False, "Only 3 octets"
    assert is_valid_ipv4("1.2.3.4.5") is False, "5 octets"
    assert is_valid_ipv4("01.2.3.4") is False, "Leading zero"
    assert is_valid_ipv4("") is False, "Empty string"
    assert is_valid_ipv4("abc.def.ghi.jkl") is False, "Non-numeric"
    assert is_valid_ipv4("1.2.3.-1") is False, "Negative octet"
    assert is_valid_ipv4("1.2.3.") is False, "Trailing dot"
    assert is_valid_ipv4(".1.2.3") is False, "Leading dot"
    assert is_valid_ipv4("1..2.3") is False, "Double dot"


# ---------------------------------------------------------------------------
# ConfigError
# ---------------------------------------------------------------------------

def test_config_error_stores_errors() -> None:
    """ConfigError stores errors and formats message properly."""
    error: ConfigError = ConfigError(["error one", "error two"])

    # .errors attribute has both errors
    assert len(error.errors) == 2, f"Expected 2 errors, got {len(error.errors)}"
    assert error.errors[0] == "error one"
    assert error.errors[1] == "error two"

    # Formatted message includes all errors
    msg: str = str(error)
    assert "error one" in msg, f"Message should contain 'error one': {msg}"
    assert "error two" in msg, f"Message should contain 'error two': {msg}"
    assert "2 error(s)" in msg, f"Message should contain '2 error(s)': {msg}"


def test_config_error_single_error() -> None:
    """Verify ConfigError works with a single error."""
    error: ConfigError = ConfigError(["only one"])
    assert len(error.errors) == 1
    assert "1 error(s)" in str(error)


# ---------------------------------------------------------------------------
# load_config valid input
# ---------------------------------------------------------------------------

def test_load_config_valid_defaults() -> None:
    """load_config returns Config with proper defaults for optional fields."""
    # Create temp SSH key file so validation passes
    ssh_key_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.pem', delete=False
    )
    ssh_key_path: str = ssh_key_file.name
    ssh_key_file.close()

    yaml_content: str = _make_valid_yaml(ssh_key_path)
    config_path: str = _write_temp_yaml(yaml_content)

    try:
        config: Config = load_config(config_path)

        # It's a Config instance
        assert isinstance(config, Config), "Should return a Config instance"

        # admin_host fields loaded
        assert config.admin_host.ip == '10.0.0.1'
        assert config.admin_host.user == 'deploy'
        assert config.admin_host.ssh_port == 22
        assert isinstance(config.admin_host.ssh_port, int)

        # cluster fields loaded
        assert config.cluster.domain == 'wire.example.com'
        assert config.cluster.kubernetes_namespace == 'wire-prod'

        # all four database IPs present
        assert config.databases.cassandra == '10.0.1.1'
        assert config.databases.elasticsearch == '10.0.1.2'
        assert config.databases.minio == '10.0.1.3'
        assert config.databases.postgresql == '10.0.1.4'

        # option defaults applied
        assert config.options.check_kubernetes is True
        assert config.options.check_databases is True
        assert config.options.check_network is True
        assert config.options.check_wire_services is True
        assert config.options.output_format == 'jsonl'
        assert config.options.output_file == 'results.jsonl'

        # top-level defaults applied
        assert config.timeout == 30, f"Default timeout should be 30, got {config.timeout}"
        assert config.kubernetes_context == '', "Default kube context should be empty"

        # wire_domain defaults to cluster.domain
        assert config.wire_domain == 'wire.example.com', \
            f"wire_domain should default to cluster.domain, got {config.wire_domain!r}"

        # kubernetes config defaults applied
        assert config.kubernetes.docker_image == 'auto', \
            f"Default docker_image should be 'auto', got {config.kubernetes.docker_image!r}"
        assert config.kubernetes.admin_home == '/home/deploy', \
            f"admin_home should default to /home/<user>, got {config.kubernetes.admin_home!r}"

        # raw is a dict
        assert isinstance(config.raw, dict)

    finally:
        os.unlink(config_path)
        os.unlink(ssh_key_path)


def test_load_config_explicit_overrides() -> None:
    """Explicit wire_domain, kubernetes_context, timeout override defaults."""
    ssh_key_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.pem', delete=False
    )
    ssh_key_path: str = ssh_key_file.name
    ssh_key_file.close()

    yaml_content: str = (
        _make_valid_yaml(ssh_key_path)
        + "wire_domain: custom.wire.io\n"
        + "kubernetes_context: staging-cluster\n"
        + "timeout: 120\n"
        + "options:\n"
        + "  check_kubernetes: false\n"
        + "  check_databases: false\n"
        + "  check_network: true\n"
        + "  check_wire_services: no\n"
        + '  output_format: "json"\n'
        + "  output_file: output.json\n"
    )
    config_path: str = _write_temp_yaml(yaml_content)

    try:
        config: Config = load_config(config_path)

        # Explicit values override defaults
        assert config.wire_domain == 'custom.wire.io'
        assert config.kubernetes_context == 'staging-cluster'
        assert config.timeout == 120

        # Options reflect explicit values
        assert config.options.check_kubernetes is False
        assert config.options.check_databases is False
        assert config.options.check_network is True
        assert config.options.check_wire_services is False
        assert config.options.output_format == 'json'
        assert config.options.output_file == 'output.json'

    finally:
        os.unlink(config_path)
        os.unlink(ssh_key_path)


# ---------------------------------------------------------------------------
# load_config error collection
# ---------------------------------------------------------------------------

def test_load_config_collects_multiple_errors() -> None:
    """load_config collects ALL validation errors, not just first."""
    yaml_content: str = (
        "admin_host:\n"
        "  ip: 999.999.999.999\n"
        "  user: deploy\n"
        '  ssh_key: "/nonexistent/key"\n'
        "  ssh_port: 99999\n"
        "cluster:\n"
        "  domain: wire.example.com\n"
        "  kubernetes_namespace: wire-prod\n"
        "databases:\n"
        "  cassandra: not_an_ip\n"
        "  elasticsearch: 10.0.1.2\n"
        "  minio: 10.0.1.3\n"
        "  postgresql: 10.0.1.4\n"
    )
    config_path: str = _write_temp_yaml(yaml_content)

    try:
        try:
            load_config(config_path)
            assert False, "Should have raised ConfigError"
        except ConfigError as e:
            # At least 3 errors: SSH key missing, port out of range, bad DB host
            assert len(e.errors) >= 3, \
                f"Expected at least 3 errors, got {len(e.errors)}: {e.errors}"

            all_errors: str = "\n".join(e.errors)
            assert "Invalid host" in all_errors, f"Should mention invalid host: {all_errors}"
            assert "not found" in all_errors, f"Should mention 'not found': {all_errors}"
            assert "1-65535" in all_errors, f"Should mention port range: {all_errors}"
    finally:
        os.unlink(config_path)


def test_load_config_missing_entire_sections() -> None:
    """Errors reported when entire required sections missing."""
    # Minimal YAML with nothing useful
    yaml_content: str = "some_key: some_value\n"
    config_path: str = _write_temp_yaml(yaml_content)

    try:
        try:
            load_config(config_path)
            assert False, "Should have raised ConfigError"
        except ConfigError as e:
            # Reports missing admin_host.ip, admin_host.user, etc.
            assert len(e.errors) >= 6, \
                f"Expected at least 6 errors for missing sections, got {len(e.errors)}: {e.errors}"
    finally:
        os.unlink(config_path)


def test_load_config_non_integer_ssh_port() -> None:
    """Non-integer ssh_port produces appropriate error."""
    ssh_key_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.pem', delete=False
    )
    ssh_key_path: str = ssh_key_file.name
    ssh_key_file.close()

    yaml_content: str = (
        "admin_host:\n"
        "  ip: 10.0.0.1\n"
        "  user: deploy\n"
        f'  ssh_key: "{ssh_key_path}"\n'
        "  ssh_port: not_a_number\n"
        "cluster:\n"
        "  domain: wire.example.com\n"
        "  kubernetes_namespace: wire-prod\n"
        "databases:\n"
        "  cassandra: 10.0.1.1\n"
        "  elasticsearch: 10.0.1.2\n"
        "  minio: 10.0.1.3\n"
        "  postgresql: 10.0.1.4\n"
    )
    config_path: str = _write_temp_yaml(yaml_content)

    try:
        try:
            load_config(config_path)
            assert False, "Should have raised ConfigError"
        except ConfigError as e:
            all_errors: str = "\n".join(e.errors)
            assert "integer" in all_errors.lower(), \
                f"Should mention integer: {all_errors}"
    finally:
        os.unlink(config_path)
        os.unlink(ssh_key_path)


# ---------------------------------------------------------------------------
# load_config file error paths
# ---------------------------------------------------------------------------

def test_load_config_missing_file() -> None:
    """ConfigError raised for non-existent config file."""
    try:
        load_config("/nonexistent/path/config.yaml")
        assert False, "Should have raised ConfigError"
    except ConfigError as e:
        assert "not found" in str(e), f"Error should mention 'not found': {e}"


def test_load_config_malformed_yaml() -> None:
    """ConfigError raised when YAML content is malformed."""
    # Odd indentation triggers ValueError in yaml parser
    yaml_content: str = "   bad_indent: value\n"
    config_path: str = _write_temp_yaml(yaml_content)

    try:
        try:
            load_config(config_path)
            assert False, "Should have raised ConfigError"
        except ConfigError as e:
            assert "YAML parse error" in str(e), \
                f"Error should mention YAML parse error: {e}"
    finally:
        os.unlink(config_path)
