"""Shared helpers for parsing Helm release data from Kubernetes secrets.

Helm stores each release as a Kubernetes secret labeled «owner=helm». The secret
name follows «sh.helm.release.v1.<name>.v<revision>», and the «.data.release»
field is double-base64-encoded (once by Helm, once by Kubernetes), gzip-compressed
JSON containing the full release info.

Functions:
    extract_revision      — parse the revision number from a secret name
    decode_chart_metadata — decompress the release payload to get the full chart metadata dict
    decode_chart_version  — convenience wrapper returning «name-version» as a string
"""

from __future__ import annotations

# External
import base64
import gzip
import json
import re
from typing import Any

# Matches the Helm secret naming convention: sh.helm.release.v1.<name>.v<revision>
_HELM_SECRET_RE: re.Pattern[str] = re.compile(r'^sh\.helm\.release\.v1\..+?\.v(\d+)$')


def extract_revision(secret_name: str) -> int:
    """Extract the revision number from a Helm secret name.

    Secret names must follow «sh.helm.release.v1.<name>.v<revision>». A regex
    validates the full prefix so arbitrary strings like «some.v3» return 0.

    Args:
        secret_name: The Kubernetes secret name.

    Returns:
        The revision number, or 0 if the name doesn't match the expected pattern.
    """
    # Match the full Helm secret pattern and extract the revision group
    match: re.Match[str] | None = _HELM_SECRET_RE.match(secret_name)

    if match:
        return int(match.group(1))

    return 0


def decode_chart_metadata(item: dict[str, Any]) -> dict[str, str]:
    """Decode chart metadata from a Helm release secret.

    Kubernetes base64-encodes all Secret «.data» values, and Helm itself stores
    its release payload as «base64(gzip(json))». So the full chain is:
    «K8s_base64( Helm_base64( gzip( json ) ) )» — two base64 decodes are needed
    before gzip decompression.

    Args:
        item: A single Kubernetes secret resource dict.

    Returns:
        The chart metadata dict (keys like «name», «version», «appVersion»),
        or an empty dict if decoding fails.
    """
    release_data: str = item.get("data", {}).get("release", "")

    if not release_data:
        return {}

    try:
        # First decode: strip the Kubernetes Secret base64 encoding
        k8s_decoded: bytes = base64.b64decode(release_data)

        # Second decode: strip Helm's own base64 encoding
        helm_decoded: bytes = base64.b64decode(k8s_decoded)

        # Validate gzip magic bytes before attempting decompression
        if len(helm_decoded) < 2 or helm_decoded[:2] != b'\x1f\x8b':
            return {}

        # Decompress the gzip payload to get the release JSON
        decompressed: bytes = gzip.decompress(helm_decoded)

        release_json: dict[str, Any] = json.loads(decompressed)

        # Chart metadata lives under «chart.metadata»
        return release_json.get("chart", {}).get("metadata", {})
    except (base64.binascii.Error, OSError, json.JSONDecodeError, KeyError):
        # Any decoding failure means we can't read the chart info
        return {}


def decode_chart_version(item: dict[str, Any]) -> str:
    """Decode the chart name and version from a Helm release secret.

    Convenience wrapper around «decode_chart_metadata» that returns the
    chart label as a single string like «wire-server-5.23.0».

    Args:
        item: A single Kubernetes secret resource dict.

    Returns:
        A string like «wire-server-5.23.0», or «unknown» if decoding fails.
    """
    chart_meta: dict[str, str] = decode_chart_metadata(item)

    if not chart_meta:
        return "unknown"

    chart_name: str = chart_meta.get("name", "unknown")
    chart_version: str = chart_meta.get("version", "unknown")

    return f"{chart_name}-{chart_version}"
