"""Checks that all required Kubernetes Secrets exist and have data.

Missing a secret and the service crashes on startup. We check zAuth keys
(brig + nginz), TURN secret, SMTP password, RabbitMQ creds, PG password,
MinIO keys, and TLS cert+key.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Secrets that must exist for Wire to work.
# Each entry: (list of possible secret names, description, list of required keys).
# We accept ANY of the listed names different deploy types (helm, WIAB, manual)
# use different naming conventions.
# When required_keys is non-empty, we verify those keys exist in the matching
# secret (e.g. TURN secret might be a key inside brig secret rather than standalone).
_REQUIRED_SECRETS: list[tuple[list[str], str, list[str]]] = [
    (
        ["brig-secrets", "brig"],
        "Brig service secrets (zAuth keys)",
        [],
    ),
    (
        ["nginz-secrets", "nginz"],
        "Nginz gateway secrets (zAuth public key)",
        [],
    ),
    (
        ["brig-turn", "brig"],
        "TURN server secret",
        ["turn-secret.txt"],
    ),
    (
        ["wire-server-tls"],
        "TLS wildcard certificate",
        ["tls.crt", "tls.key"],
    ),
]

# Additional secrets to check if they exist (may have different names per deployment)
_OPTIONAL_SECRET_PATTERNS: list[str] = [
    "smtp",
    "rabbitmq",
    "minio",
    "postgresql",
    "postgres",
]


class RequiredSecretsPresent(BaseTarget):
    """Checks that required Kubernetes Secrets exist and have data.

    Queries secrets in the Wire namespace and verifies each required secret
    exists and contains non-empty data.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "All required Kubernetes Secrets present and non-empty"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Missing secrets just crash services on startup. We check zAuth keys, TURN secret, "
            "TLS cert, and optional SMTP/RabbitMQ/MinIO/PostgreSQL secrets."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is boolean."""
        return ""

    def collect(self) -> bool:
        """Check that required secrets exist and have data.

        Returns:
            True if all required secrets are present, False otherwise.
        """
        self.terminal.step("Checking required Kubernetes secrets...")

        # Get all secrets in the namespace
        cmd_result, data = self.run_kubectl("secrets")

        if data is None:
            raise RuntimeError("Failed to query secrets from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        # Build a map of secret names to their data keys
        secret_map: dict[str, set[str]] = {}
        for item in items:
            name: str = item.get("metadata", {}).get("name", "")
            data_keys: dict = item.get("data") or {}
            secret_map[name] = set(data_keys.keys())

        # Check required secrets accept any of the alternative names
        tls_desc: str = "TLS wildcard certificate"

        # Track the exact string for TLS in empty list so bypass can remove it by exact match
        # (entry is «wire-server-tls (empty)», not «... (TLS wildcard certificate)»,
        # so substring search would miss it)
        tls_empty_entry: str | None = None

        # Track exact string for TLS wrong-key case so bypass can remove by exact match
        # (entry like «wire-server-tls (missing keys: tls.crt, tls.key)» doesn't contain
        # tls_desc so substring filter would miss it)
        tls_missing_entry: str | None = None

        present: list[str] = []
        missing: list[str] = []
        empty: list[str] = []

        for possible_names, desc, required_keys in _REQUIRED_SECRETS:
            found_name: str | None = None
            for candidate in possible_names:
                if candidate in secret_map:
                    found_name = candidate
                    break

            if found_name is None:
                # None of the names matched
                missing.append(f"{possible_names[0]} ({desc})")
                continue

            keys_in_secret: set[str] = secret_map[found_name]

            if len(keys_in_secret) == 0:
                empty_entry: str = f"{found_name} (empty)"
                empty.append(empty_entry)
                # Remember the exact string so the TLS bypass can remove it by exact match
                if desc == tls_desc:
                    tls_empty_entry = empty_entry
                continue

            # If specific keys are required, verify they exist in the secret
            if required_keys:
                missing_keys: list[str] = [
                    k for k in required_keys if k not in keys_in_secret
                ]
                if missing_keys:
                    missing_entry: str = f"{found_name} (missing keys: {', '.join(missing_keys)})"
                    missing.append(missing_entry)
                    # Remember exact string so TLS bypass can remove it entry contains
                    # «missing keys: …» not tls_desc, so substring filter would miss it
                    if desc == tls_desc:
                        tls_missing_entry = missing_entry
                    continue

            present.append(found_name)

        # Also search for TLS cert/key in any secret (WIAB uses weird auto-generated names).
        # Check if wire-server-tls was added to present. Using any(...) on all present names
        # would be wrong an unrelated secret might have tls.crt/tls.key.
        tls_found_in_required: bool = "wire-server-tls" in present
        if not tls_found_in_required:
            # Check if any secret has both tls.crt and tls.key
            for name, keys in secret_map.items():
                if "tls.crt" in keys and "tls.key" in keys:
                    # Found a TLS secret remove any missing/empty entries for TLS check.
                    #
                    # Two formats can appear in missing:
                    #   1. «wire-server-tls (TLS wildcard certificate)» secret absent
                    #   2. «wire-server-tls (missing keys: tls.crt, tls.key)» exists but
                    #      incomplete (doesn't contain tls_desc, so need exact match)
                    missing = [m for m in missing if tls_desc not in m
                               and (tls_missing_entry is None or m != tls_missing_entry)]
                    # Filter by exact match entry is «wire-server-tls (empty)» not
                    # «... (TLS wildcard certificate)» so substring search would miss it
                    empty = [e for e in empty if tls_empty_entry is None or e != tls_empty_entry]
                    present.append(f"{name} (TLS)")
                    break

        # Check optional patterns just report if they exist
        optional_found: int = 0
        for pattern in _OPTIONAL_SECRET_PATTERNS:
            for name in secret_map:
                if pattern in name.lower():
                    optional_found += 1
                    break

        all_ok: bool = len(missing) == 0 and len(empty) == 0

        if all_ok:
            self._health_info = (
                f"All {len(_REQUIRED_SECRETS)} required secrets present, "
                f"{optional_found} optional patterns matched"
            )
        else:
            issues: list[str] = missing + empty
            self._health_info = f"Issues: {', '.join(issues)}"

        return all_ok
