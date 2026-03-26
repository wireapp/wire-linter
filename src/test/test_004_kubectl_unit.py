"""Unit tests for the kubectl command wrapper module.

Covers kubectl_get command construction, JSON parsing, error handling,
and kubectl_raw argument passthrough. Uses unittest.mock to patch
run_command since kubectl is not available in the test environment.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
from typing import Any

from src.lib.command import CommandResult
from src.lib.kubectl import kubectl_get, kubectl_raw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_result(
    stdout: str = '',
    stderr: str = '',
    exit_code: int = 0,
) -> CommandResult:
    """Build a mock CommandResult for testing."""
    return CommandResult(
        command='kubectl mock',
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=0.1,
        success=(exit_code == 0),
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# kubectl_get command construction
# ---------------------------------------------------------------------------

@patch('src.lib.kubectl.run_command')
def test_kubectl_get_basic(mock_run: MagicMock) -> None:
    """kubectl_get should build a basic 'kubectl get <resource> -o json' command."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    kubectl_get('nodes')

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert cmd_list[0] == 'kubectl', f"First arg should be 'kubectl', got {cmd_list[0]!r}"
    assert 'get' in cmd_list, "Should have 'get' subcommand"
    assert 'nodes' in cmd_list, "Should have resource 'nodes'"
    assert '-o' in cmd_list, "Should have -o flag"
    assert 'json' in cmd_list, "Should have 'json' output format"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_with_namespace(mock_run: MagicMock) -> None:
    """namespace flag should be added when provided."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    kubectl_get('pods', namespace='wire-prod')

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert '-n' in cmd_list, "Should have -n flag"
    ns_idx: int = cmd_list.index('-n')
    assert cmd_list[ns_idx + 1] == 'wire-prod', \
        f"Namespace should be 'wire-prod', got {cmd_list[ns_idx + 1]!r}"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_with_selector(mock_run: MagicMock) -> None:
    """label selector should be added when provided."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    kubectl_get('pods', selector='app=brig')

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert '-l' in cmd_list, "Should have -l flag"
    sel_idx: int = cmd_list.index('-l')
    assert cmd_list[sel_idx + 1] == 'app=brig', \
        f"Selector should be 'app=brig', got {cmd_list[sel_idx + 1]!r}"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_all_namespaces(mock_run: MagicMock) -> None:
    """--all-namespaces flag should win over namespace."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    # when both are passed, all_namespaces takes precedence
    kubectl_get('pods', namespace='should-be-ignored', all_namespaces=True)

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert '--all-namespaces' in cmd_list, "Should have --all-namespaces"
    assert '-n' not in cmd_list, "Should NOT have -n when all_namespaces=True"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_with_context(mock_run: MagicMock) -> None:
    """context flag should be added when provided."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    kubectl_get('nodes', context='prod-cluster')

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert '--context' in cmd_list, "Should have --context flag"
    ctx_idx: int = cmd_list.index('--context')
    assert cmd_list[ctx_idx + 1] == 'prod-cluster', \
        f"Context should be 'prod-cluster', got {cmd_list[ctx_idx + 1]!r}"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_empty_context_omitted(mock_run: MagicMock) -> None:
    """empty context string should not add --context flag."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    kubectl_get('nodes', context='')

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert '--context' not in cmd_list, "Empty context should not add --context"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_custom_timeout(mock_run: MagicMock) -> None:
    """custom timeout should be passed to run_command."""
    mock_run.return_value = _make_mock_result(stdout='{}')

    kubectl_get('nodes', timeout=60)

    # check the timeout kwarg
    call_kwargs: dict[str, Any] = mock_run.call_args[1]
    assert call_kwargs.get('timeout') == 60, \
        f"Expected timeout=60, got {call_kwargs.get('timeout')}"


# ---------------------------------------------------------------------------
# kubectl_get JSON parsing
# ---------------------------------------------------------------------------

@patch('src.lib.kubectl.run_command')
def test_kubectl_get_parses_json(mock_run: MagicMock) -> None:
    """kubectl_get should parse valid JSON output."""
    json_output: dict[str, Any] = {
        'apiVersion': 'v1',
        'kind': 'NodeList',
        'items': [{'metadata': {'name': 'node-1'}}],
    }
    mock_run.return_value = _make_mock_result(stdout=json.dumps(json_output))

    result: CommandResult
    parsed: Any
    result, parsed = kubectl_get('nodes')

    assert parsed is not None, "Parsed JSON should not be None"
    assert parsed['kind'] == 'NodeList', f"Expected 'NodeList', got {parsed.get('kind')!r}"
    assert len(parsed['items']) == 1, f"Expected 1 item, got {len(parsed['items'])}"
    assert parsed['items'][0]['metadata']['name'] == 'node-1'


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_empty_stdout(mock_run: MagicMock) -> None:
    """empty stdout should return None for parsed data."""
    mock_run.return_value = _make_mock_result(stdout='', exit_code=1)

    result: CommandResult
    parsed: Any
    result, parsed = kubectl_get('nodes')

    assert parsed is None, "Empty stdout should result in None parsed data"


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_invalid_json(mock_run: MagicMock) -> None:
    """invalid JSON should return None without raising."""
    mock_run.return_value = _make_mock_result(
        stdout='error: the server has asked for the client to provide credentials',
        exit_code=1,
    )

    result: CommandResult
    parsed: Any
    result, parsed = kubectl_get('nodes')

    assert parsed is None, "Invalid JSON should result in None parsed data"
    assert result.exit_code == 1


@patch('src.lib.kubectl.run_command')
def test_kubectl_get_whitespace_stdout(mock_run: MagicMock) -> None:
    """whitespace-only stdout should return None."""
    mock_run.return_value = _make_mock_result(stdout='   \n  \n')

    result: CommandResult
    parsed: Any
    result, parsed = kubectl_get('nodes')

    assert parsed is None, "Whitespace-only stdout should result in None parsed data"


# ---------------------------------------------------------------------------
# kubectl_raw argument passthrough
# ---------------------------------------------------------------------------

@patch('src.lib.kubectl.run_command')
def test_kubectl_raw_basic(mock_run: MagicMock) -> None:
    """kubectl_raw should pass args directly after 'kubectl'."""
    mock_run.return_value = _make_mock_result(stdout='node-1  100m  20%')

    result: CommandResult = kubectl_raw(['top', 'nodes'])

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert cmd_list[0] == 'kubectl'
    assert 'top' in cmd_list
    assert 'nodes' in cmd_list
    # no -o json here, that's only for kubectl_get
    assert '-o' not in cmd_list


@patch('src.lib.kubectl.run_command')
def test_kubectl_raw_with_context(mock_run: MagicMock) -> None:
    """kubectl_raw should add context flag when provided."""
    mock_run.return_value = _make_mock_result()

    kubectl_raw(['version'], context='staging')

    cmd_list: list[str] = mock_run.call_args[0][0]

    assert '--context' in cmd_list
    ctx_idx: int = cmd_list.index('--context')
    assert cmd_list[ctx_idx + 1] == 'staging'


@patch('src.lib.kubectl.run_command')
def test_kubectl_raw_returns_result(mock_run: MagicMock) -> None:
    """kubectl_raw should return the CommandResult from run_command."""
    expected: CommandResult = _make_mock_result(stdout='version info')
    mock_run.return_value = expected

    result: CommandResult = kubectl_raw(['version'])

    assert result is expected, "Should return the exact CommandResult"
    assert result.stdout == 'version info'
