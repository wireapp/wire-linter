"""Unit tests for the HTTP client module.

Covers http_get with mocked urllib responses (success, HTTP errors, connection
errors, general exceptions), HttpResult field structure, and http_get_via_ssh
delegation to SSH(config).to(host).run().
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, PropertyMock
import urllib.error
import urllib.request

from src.lib.command import CommandResult
from src.lib.http_client import http_get, http_get_via_ssh, HttpResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(
    body: bytes = b'OK',
    status: int = 200,
    headers: list[tuple[str, str]] | None = None,
) -> MagicMock:
    """Build a mock urllib response object."""
    mock_response: MagicMock = MagicMock()
    mock_response.read.return_value = body
    mock_response.status = status
    mock_response.getheaders.return_value = headers or [('Content-Type', 'text/plain')]
    return mock_response


def _make_mock_config() -> MagicMock:
    """Build a mock Config object with admin_host credentials."""
    config: MagicMock = MagicMock()
    config.admin_host.user = 'deploy'
    config.admin_host.ssh_key = '/path/to/key.pem'
    config.admin_host.ssh_port = 22
    config.timeout = 30
    return config


# ---------------------------------------------------------------------------
# http_get successful responses
# ---------------------------------------------------------------------------

@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_get_success(mock_urlopen: MagicMock) -> None:
    """http_get should return correct HttpResult for a 200 response."""
    mock_urlopen.return_value = _make_mock_response(
        body=b'{"status": "ok"}',
        status=200,
        headers=[('Content-Type', 'application/json')],
    )

    result: HttpResult = http_get('http://example.com/health')

    assert result.success is True, f"Expected success, got success={result.success}"
    assert result.status_code == 200, f"Expected 200, got {result.status_code}"
    assert result.body == '{"status": "ok"}', f"Unexpected body: {result.body!r}"
    assert result.url == 'http://example.com/health'
    assert result.error is None, f"Expected no error, got {result.error!r}"
    assert result.duration_seconds >= 0
    assert 'Content-Type' in result.headers


@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_get_301_is_success(mock_urlopen: MagicMock) -> None:
    """3xx status codes should be treated as success."""
    mock_urlopen.return_value = _make_mock_response(
        body=b'redirecting',
        status=301,
    )

    result: HttpResult = http_get('http://example.com/old')

    assert result.success is True, "3xx should be success"
    assert result.status_code == 301


# ---------------------------------------------------------------------------
# http_get HTTP error responses
# ---------------------------------------------------------------------------

@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_get_http_error(mock_urlopen: MagicMock) -> None:
    """http_get should handle HTTPError (4xx/5xx) gracefully."""
    # create a proper HTTPError
    error: urllib.error.HTTPError = urllib.error.HTTPError(
        url='http://example.com/missing',
        code=404,
        msg='Not Found',
        hdrs=MagicMock(),
        fp=None,
    )
    # mock the read method on the error object
    error.read = MagicMock(return_value=b'page not found')
    error.headers = MagicMock()
    error.headers.items.return_value = [('Content-Type', 'text/html')]
    mock_urlopen.side_effect = error

    result: HttpResult = http_get('http://example.com/missing')

    assert result.success is False, "404 should not be success"
    assert result.status_code == 404, f"Expected 404, got {result.status_code}"
    assert result.body == 'page not found', f"Expected error body, got {result.body!r}"
    assert result.error is None, "HTTPError should not set error field (it's a response)"


@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_get_500_error(mock_urlopen: MagicMock) -> None:
    """http_get should handle 500 server error."""
    error: urllib.error.HTTPError = urllib.error.HTTPError(
        url='http://example.com/api',
        code=500,
        msg='Internal Server Error',
        hdrs=MagicMock(),
        fp=None,
    )
    error.read = MagicMock(return_value=b'server error')
    error.headers = MagicMock()
    error.headers.items.return_value = []
    mock_urlopen.side_effect = error

    result: HttpResult = http_get('http://example.com/api')

    assert result.success is False
    assert result.status_code == 500


# ---------------------------------------------------------------------------
# http_get connection errors
# ---------------------------------------------------------------------------

@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_get_url_error(mock_urlopen: MagicMock) -> None:
    """http_get should handle URLError (DNS, connection refused, etc.)."""
    mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

    result: HttpResult = http_get('http://unreachable.invalid/health')

    assert result.success is False, "Connection error should not be success"
    assert result.status_code == 0, f"Expected status_code 0, got {result.status_code}"
    assert result.body == '', "Body should be empty on connection error"
    assert result.error is not None, "Error should be set for connection errors"
    assert 'Connection refused' in result.error, f"Error should mention reason: {result.error!r}"


@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_get_general_exception(mock_urlopen: MagicMock) -> None:
    """http_get should handle unexpected exceptions gracefully."""
    mock_urlopen.side_effect = RuntimeError('unexpected failure')

    result: HttpResult = http_get('http://example.com/fail')

    assert result.success is False
    assert result.status_code == 0
    assert 'unexpected failure' in result.error


# ---------------------------------------------------------------------------
# http_get HttpResult structure
# ---------------------------------------------------------------------------

@patch('src.lib.http_client.urllib.request.urlopen')
def test_http_result_fields(mock_urlopen: MagicMock) -> None:
    """all HttpResult fields should have correct types."""
    mock_urlopen.return_value = _make_mock_response()

    result: HttpResult = http_get('http://example.com')

    assert isinstance(result.url, str), "url should be str"
    assert isinstance(result.status_code, int), "status_code should be int"
    assert isinstance(result.body, str), "body should be str"
    assert isinstance(result.headers, dict), "headers should be dict"
    assert isinstance(result.duration_seconds, float), "duration_seconds should be float"
    assert isinstance(result.success, bool), "success should be bool"
    assert result.error is None or isinstance(result.error, str), "error should be str or None"


# ---------------------------------------------------------------------------
# http_get_via_ssh delegation
# ---------------------------------------------------------------------------

@patch('src.lib.http_client.SSH')
def test_http_get_via_ssh_delegates(mock_ssh_class: MagicMock) -> None:
    """http_get_via_ssh should call SSH(config).to(ssh_host).run() with a curl command."""
    expected_result: CommandResult = CommandResult(
        command='ssh mock curl',
        exit_code=0,
        stdout='{"status": "ok"}\n200',
        stderr='',
        duration_seconds=1.5,
        success=True,
        timed_out=False,
    )

    # wire up the fluent chain: SSH(config).to(host).run(cmd)
    mock_target: MagicMock = MagicMock()
    mock_target.run.return_value = expected_result
    mock_ssh_class.return_value.to.return_value = mock_target

    config: MagicMock = _make_mock_config()
    result: CommandResult = http_get_via_ssh(
        url='http://localhost:8080/health',
        ssh_host='10.0.0.1',
        config=config,
        timeout=15,
    )

    # check SSH was instantiated with config
    mock_ssh_class.assert_called_once_with(config)

    # check .to() was called with the provided SSH host
    mock_ssh_class.return_value.to.assert_called_once_with('10.0.0.1')

    # check .run() was called once
    assert mock_target.run.call_count == 1

    # check the curl command has the right parts
    curl_cmd: str = mock_target.run.call_args[0][0]
    assert 'curl' in curl_cmd, \
        f"Remote command should contain 'curl': {curl_cmd!r}"
    assert 'http://localhost:8080/health' in curl_cmd, \
        f"Remote command should contain URL: {curl_cmd!r}"

    # result should be passed through unchanged
    assert result is expected_result


@patch('src.lib.http_client.SSH')
def test_http_get_via_ssh_curl_timeout(mock_ssh_class: MagicMock) -> None:
    """curl --max-time should be set to the provided timeout."""
    mock_target: MagicMock = MagicMock()
    mock_target.run.return_value = CommandResult(
        command='ssh mock',
        exit_code=0,
        stdout='',
        stderr='',
        duration_seconds=0.1,
        success=True,
        timed_out=False,
    )
    mock_ssh_class.return_value.to.return_value = mock_target

    config: MagicMock = _make_mock_config()
    http_get_via_ssh(
        url='http://localhost:9200/_cluster/health',
        ssh_host='10.0.0.1',
        config=config,
        timeout=30,
    )

    curl_cmd: str = mock_target.run.call_args[0][0]
    assert '--max-time 30' in curl_cmd, \
        f"curl should have --max-time 30: {curl_cmd!r}"
