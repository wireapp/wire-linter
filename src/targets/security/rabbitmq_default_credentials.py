"""Checks whether RabbitMQ is using default guest/guest credentials.

Default RabbitMQ credentials are a security risk any pod in the cluster
can access the message broker without proper auth. Production deployments
should always use strong, unique credentials.
"""

from __future__ import annotations

# External
import base64
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Common default credential pairs to check (username, password)
_DEFAULT_CREDENTIALS: list[tuple[str, str]] = [
    ("guest", "guest"),
]


class RabbitmqDefaultCredentials(BaseTarget):
    """Checks whether RabbitMQ Kubernetes secrets contain default credentials.

    Queries secrets in the Wire namespace, finds the RabbitMQ-related secret,
    decodes the username and password, and checks against known defaults.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "RabbitMQ credentials are not default (guest/guest)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Default RabbitMQ credentials (guest/guest) let any pod in the cluster "
            "access the message broker. Production deployments need strong, "
            "unique credentials."
        )

    def collect(self) -> bool:
        """Check RabbitMQ credentials in Kubernetes secrets.

        Returns:
            True if credentials are non-default (safe), False if default (risky).
        """
        self.terminal.step("Checking RabbitMQ credentials in Kubernetes secrets...")

        # Get all secrets in the namespace
        cmd_result, data = self.run_kubectl("secrets")

        if data is None:
            raise RuntimeError("Failed to query secrets from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        # Collect (username, password) pairs from every RabbitMQ-related secret
        # so that ALL secrets are checked not just the last one encountered.
        credential_pairs: list[tuple[str | None, str | None]] = []

        for item in items:
            name: str = item.get("metadata", {}).get("name", "")
            secret_data: dict[str, str] = item.get("data") or {}

            # Skip Helm release secrets (they're compressed blobs, not creds)
            if name.startswith("sh.helm.release."):
                continue

            # Only examine secrets whose name contains "rabbitmq"
            if "rabbitmq" not in name.lower():
                continue

            # Extract username and password from this individual secret
            secret_username: str | None = None
            secret_password: str | None = None

            for key, b64_value in secret_data.items():
                key_lower: str = key.lower()
                try:
                    decoded: str = base64.b64decode(b64_value).decode("utf-8")
                except Exception:
                    continue

                if "username" in key_lower or "user" in key_lower:
                    secret_username = decoded
                elif "password" in key_lower or "pass" in key_lower:
                    secret_password = decoded

            # Only record this secret if it contained at least one credential field
            if secret_username is not None or secret_password is not None:
                credential_pairs.append((secret_username, secret_password))

        # If no RabbitMQ secret found at all
        if not credential_pairs:
            self._health_info = "No RabbitMQ credentials found in secrets"
            return True  # Can't check, nothing to flag

        # Fail if ANY secret contains a known default credential pair -
        # a single weak secret is enough to represent a security risk.
        for secret_username, secret_password in credential_pairs:
            for default_user, default_pass in _DEFAULT_CREDENTIALS:
                if secret_username == default_user and secret_password == default_pass:
                    self._health_info = (
                        "RabbitMQ using known default credentials (security risk)"
                    )
                    return False

        self._health_info = "RabbitMQ credentials are non-default"
        return True
