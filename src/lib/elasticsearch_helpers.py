"""Shared helpers for Elasticsearch target collectors.

Centralises the credential-handling logic so all ES targets use
one properly-escaped code path instead of duplicating it.
"""

from __future__ import annotations

# External
import shlex


def build_es_auth_flag(username: str | None, password: str | None) -> str:
    """Build the curl ``-u`` flag for Elasticsearch authentication.

    Uses ``shlex.quote()`` to safely escape credentials that may contain
    shell metacharacters (single quotes, spaces, semicolons, etc.).

    Args:
        username: ES username from config, or None / empty when auth is disabled.
        password: ES password from config, or None / empty.

    Returns:
        A string like ``-u 'user:pass' `` (with trailing space) when credentials
        are provided, or an empty string when they are not.
    """
    if not username:
        return ""

    # both username and password must be present to send credentials
    if not password:
        return ""

    # Combine user:pass and let shlex.quote wrap it in shell-safe quoting
    credential_pair: str = f"{username}:{password}"
    return f"-u {shlex.quote(credential_pair)} "
