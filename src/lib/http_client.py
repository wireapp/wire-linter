"""HTTP client built on urllib. Direct requests or tunneled through SSH for
services you can't reach directly.
"""

from __future__ import annotations

import shlex
import ssl
import time
import http.client
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.lib.command import CommandResult
from src.lib.ssh import SSH

if TYPE_CHECKING:
    from src.lib.config import Config


@dataclass
class HttpResult:
    """What came back from an HTTP request."""

    url: str                         # URL that was requested
    status_code: int                 # HTTP status code, 0 if connection failed entirely
    body: str                        # response body text
    headers: dict[str, list[str]]    # response headers, preserving duplicate names
    duration_seconds: float          # how long it took
    success: bool                    # True if 200 <= status_code < 400
    error: str | None                # error description on failure, None otherwise


def _collect_headers(raw: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Convert a list of (name, value) header tuples to a dict preserving duplicates.

    HTTP allows multiple headers with the same name (e.g. Set-Cookie, Link).
    Plain dict() keeps only the last value per name; this collects all values.

    Args:
        raw: List of (header-name, header-value) tuples as returned by getheaders().

    Returns:
        Dict mapping each header name to its list of values in order received.
    """
    headers: dict[str, list[str]] = {}
    for name, value in raw:
        # accumulate every occurrence under the same key
        headers.setdefault(name, []).append(value)
    return headers


def _build_ssl_context(ca_bundle: str = "") -> ssl.SSLContext:
    """Build an SSL context for HTTPS requests.

    Args:
        ca_bundle: Path to a custom CA bundle file. When provided, that CA is
            used for verification. When empty, SSL verification is disabled
            entirely (needed for self-signed certs in on-prem deployments).

    Returns:
        An ssl.SSLContext configured appropriately.
    """
    if ca_bundle:
        # trust only the provided CA bundle
        context: ssl.SSLContext = ssl.create_default_context(cafile=ca_bundle)
    else:
        # skip verification for self-signed / unknown CA certs
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return context


def http_get(
    url: str,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
    ca_bundle: str = "",
) -> HttpResult:
    """GET the given URL.

    Args:
        url: Full URL.
        timeout: Request timeout in seconds.
        headers: Optional headers to include.
        ca_bundle: Path to a custom CA bundle file. When provided, that CA is
            used for certificate verification. When empty (default), SSL
            certificate verification is disabled so self-signed certs work.

    Returns:
        HttpResult with status, body, headers, and timing.
    """
    # how long does this take
    start_time: float = time.monotonic()

    # build the request
    request: urllib.request.Request = urllib.request.Request(
        url,
        headers=headers or {},
        method='GET',
    )

    # build SSL context that handles self-signed certs
    ssl_context: ssl.SSLContext = _build_ssl_context(ca_bundle)

    try:
        response: http.client.HTTPResponse = urllib.request.urlopen(
            request, timeout=timeout, context=ssl_context
        )

        # read body
        body: str = response.read().decode('utf-8', errors='replace')

        # grab headers, preserving all values for duplicate names
        response_headers: dict[str, list[str]] = _collect_headers(response.getheaders())

        status_code: int = response.status

        duration: float = time.monotonic() - start_time

        return HttpResult(
            url=url,
            status_code=status_code,
            body=body,
            headers=response_headers,
            duration_seconds=duration,
            success=(200 <= status_code < 400),
            error=None,
        )

    except urllib.error.HTTPError as error:
        # HTTPError also exposes the response body
        duration: float = time.monotonic() - start_time

        # grab the error body
        body = error.read().decode('utf-8', errors='replace')

        return HttpResult(
            url=url,
            status_code=error.code,
            body=body,
            headers=_collect_headers(list(error.headers.items())),
            duration_seconds=duration,
            success=False,
            error=None,
        )

    except urllib.error.URLError as error:
        # dns fail, connection refused, etc.
        duration: float = time.monotonic() - start_time

        return HttpResult(
            url=url,
            status_code=0,
            body='',
            headers={},
            duration_seconds=duration,
            success=False,
            error=str(error.reason),
        )

    except Exception as exc:
        # anything else
        duration: float = time.monotonic() - start_time

        return HttpResult(
            url=url,
            status_code=0,
            body='',
            headers={},
            duration_seconds=duration,
            success=False,
            error=str(exc),
        )


def http_get_via_ssh(
    url: str,
    ssh_host: str,
    config: 'Config',
    timeout: int = 15,
    ca_bundle: str = "",
) -> CommandResult:
    """GET a URL via curl on a remote host.

    Use when the service isn't reachable directly from the runner. SSH to ssh_host
    and run curl there instead.

    Args:
        url: URL to hit (as seen from ssh_host).
        ssh_host: Host to SSH into.
        config: SSH credentials from the runner config.
        timeout: Curl timeout in seconds.
        ca_bundle: Path to a CA bundle file on the remote host. When provided,
            curl uses --cacert to verify against that CA. When empty (default),
            curl uses -k to skip verification (matching http_get behavior for
            self-signed certs).

    Returns:
        CommandResult with curl's output.
    """
    # decide SSL flags: use the provided CA bundle, or skip verification entirely
    if ca_bundle:
        ssl_flag: str = f"--cacert {shlex.quote(ca_bundle)}"
    else:
        ssl_flag = "-k"

    # silent, body to stdout, append status code at the end
    curl_command: str = f"curl -s {ssl_flag} -o - -w '\\n%{{http_code}}' --max-time {timeout} {shlex.quote(url)}"

    # SSH over and run it
    return SSH(config).to(ssh_host).run(curl_command)
