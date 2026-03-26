"""Unit tests for the SSH command execution module.

Covers SSHTarget argument construction and SSH config credential extraction.
Uses unittest.mock to patch run_command since actual SSH connections are not
available in the test environment.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from typing import Any

from src.lib.command import CommandResult
from src.lib.ssh import SSH, SSHTarget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_result(
    command: str = 'ssh mock',
    stdout: str = '',
    stderr: str = '',
    exit_code: int = 0,
) -> CommandResult:
    """Build a CommandResult for mocking run_command returns."""
    return CommandResult(
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=0.1,
        success=(exit_code == 0),
        timed_out=False,
    )


def _make_mock_config() -> MagicMock:
    """Build a mock Config with admin_host credentials."""
    config: MagicMock = MagicMock()
    config.admin_host.user = 'deploy'
    config.admin_host.ssh_key = '/path/to/key.pem'
    config.admin_host.ssh_port = 22
    config.timeout = 30
    return config


# ---------------------------------------------------------------------------
# SSHTarget argument construction
# ---------------------------------------------------------------------------

@patch('src.lib.ssh.run_command')
def test_run_ssh_command_builds_correct_args(mock_run: MagicMock) -> None:
    """SSHTarget constructs SSH command with all required flags."""
    mock_run.return_value = _make_mock_result()

    SSHTarget(
        host='10.0.0.1',
        user='deploy',
        key='/path/to/key.pem',
        port=22,
        timeout=30,
    ).run('uptime')

    # run_command called once
    assert mock_run.call_count == 1, f"Expected 1 call, got {mock_run.call_count}"

    # Extract command list
    call_args: tuple[Any, ...] = mock_run.call_args
    cmd_list: list[str] = call_args[0][0]

    # SSH binary present
    assert cmd_list[0] == 'ssh', f"First element should be 'ssh', got {cmd_list[0]!r}"

    # StrictHostKeyChecking=no present
    assert '-o' in cmd_list, "Should have -o flag"
    strict_idx: int = cmd_list.index('StrictHostKeyChecking=no')
    assert cmd_list[strict_idx - 1] == '-o', "StrictHostKeyChecking should follow -o"

    # BatchMode=yes present
    batch_idx: int = cmd_list.index('BatchMode=yes')
    assert cmd_list[batch_idx - 1] == '-o', "BatchMode should follow -o"

    # ConnectTimeout=10 present
    connect_idx: int = cmd_list.index('ConnectTimeout=10')
    assert cmd_list[connect_idx - 1] == '-o', "ConnectTimeout should follow -o"

    # SSH key present
    key_idx: int = cmd_list.index('/path/to/key.pem')
    assert cmd_list[key_idx - 1] == '-i', "Key path should follow -i"

    # Port present
    port_idx: int = cmd_list.index('22')
    assert cmd_list[port_idx - 1] == '-p', "Port should follow -p"

    # user@host present
    assert 'deploy@10.0.0.1' in cmd_list, "Should have user@host"

    # Remote command present
    assert 'uptime' in cmd_list, "Should have the remote command"

    # Timeout passed to run_command
    assert call_args[1]['timeout'] == 30 or call_args.kwargs.get('timeout') == 30


@patch('src.lib.ssh.run_command')
def test_run_ssh_command_custom_port(mock_run: MagicMock) -> None:
    """Non-default SSH port passed correctly."""
    mock_run.return_value = _make_mock_result()

    SSHTarget(
        host='10.0.0.5',
        user='admin',
        key='/keys/id_rsa',
        port=2222,
        timeout=15,
    ).run('hostname')

    cmd_list: list[str] = mock_run.call_args[0][0]

    # Custom port present
    port_idx: int = cmd_list.index('2222')
    assert cmd_list[port_idx - 1] == '-p', "Custom port should follow -p"

    # Custom user@host present
    assert 'admin@10.0.0.5' in cmd_list


@patch('src.lib.ssh.run_command')
def test_run_ssh_command_returns_result(mock_run: MagicMock) -> None:
    """SSHTarget.run() returns CommandResult from run_command."""
    expected_result: CommandResult = _make_mock_result(
        stdout='10:30:00 up 5 days',
        exit_code=0,
    )
    mock_run.return_value = expected_result

    result: CommandResult = SSHTarget(
        host='10.0.0.1',
        user='deploy',
        key='/path/to/key.pem',
        port=22,
        timeout=30,
    ).run('uptime')

    assert result is expected_result, "Should return the exact CommandResult from run_command"
    assert result.stdout == '10:30:00 up 5 days'


@patch('src.lib.ssh.run_command')
def test_run_ssh_command_default_port(mock_run: MagicMock) -> None:
    """SSH port 22 passed correctly."""
    mock_run.return_value = _make_mock_result()

    SSHTarget(
        host='10.0.0.1',
        user='deploy',
        key='/path/to/key.pem',
        port=22,
        timeout=30,
    ).run('ls')

    cmd_list: list[str] = mock_run.call_args[0][0]
    port_idx: int = cmd_list.index('22')
    assert cmd_list[port_idx - 1] == '-p', "Default port 22 should be present"


# ---------------------------------------------------------------------------
# SSH config credential extraction
# ---------------------------------------------------------------------------

@patch('src.lib.ssh.run_command')
def test_run_db_command_uses_config_credentials(mock_run: MagicMock) -> None:
    """SSH.to() extracts SSH credentials from config.admin_host."""
    mock_run.return_value = _make_mock_result()
    config: MagicMock = _make_mock_config()

    SSH(config).to('10.0.1.1').run('nodetool status')

    assert mock_run.call_count == 1
    cmd_list: list[str] = mock_run.call_args[0][0]

    # Uses admin_host credentials from config
    assert 'deploy@10.0.1.1' in cmd_list, "Should connect as deploy to db_host"

    key_idx: int = cmd_list.index('/path/to/key.pem')
    assert cmd_list[key_idx - 1] == '-i', "Should use SSH key from config"

    port_idx: int = cmd_list.index('22')
    assert cmd_list[port_idx - 1] == '-p', "Should use SSH port from config"

    # Remote command present
    assert 'nodetool status' in cmd_list


@patch('src.lib.ssh.run_command')
def test_run_db_command_uses_config_timeout(mock_run: MagicMock) -> None:
    """SSH.to().run() passes config.timeout to run_command."""
    mock_run.return_value = _make_mock_result()
    config: MagicMock = _make_mock_config()
    config.timeout = 60

    SSH(config).to('10.0.1.2').run('curl localhost:9200')

    # Timeout from config.timeout
    call_kwargs: dict[str, Any] = mock_run.call_args[1] if mock_run.call_args[1] else {}
    timeout_value: int = call_kwargs.get('timeout', mock_run.call_args[0][1] if len(mock_run.call_args[0]) > 1 else None)
    assert timeout_value == 60, f"Expected timeout 60 from config, got {timeout_value}"
