"""Shell-safety validation for values interpolated into shell commands.

Provides validate_domain_for_shell() which checks that a domain string
conforms to RFC 1123, ensuring no shell metacharacters (backticks, $, ;,
pipes, etc.) can sneak into commands built with string interpolation.

Used by DNS targets that pass user-supplied domain strings into dig commands
over SSH.
"""

from __future__ import annotations

import re

# RFC 1123 hostname: alphanumeric labels separated by dots, hyphens allowed
# in the middle. This rejects shell metacharacters (backticks, $, ;, etc.).
DOMAIN_RE: re.Pattern[str] = re.compile(
    r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
)


def validate_domain_for_shell(domain: str) -> None:
    """Validate that domain is safe to interpolate into a shell command.

    Checks against RFC 1123 hostname pattern, which only allows
    alphanumerics, hyphens, and dots — no shell metacharacters.

    Args:
        domain: Domain string to validate.

    Raises:
        ValueError: If domain contains characters outside RFC 1123.
    """
    # RFC 1123 caps the total hostname length at 253 characters.
    if len(domain) > 253:
        raise ValueError(
            f"Refusing to build shell command: {domain!r} exceeds the 253-character RFC 1123 hostname limit"
        )
    if not domain or not DOMAIN_RE.match(domain):
        raise ValueError(
            f"Refusing to build shell command: {domain!r} is not a valid domain"
        )
