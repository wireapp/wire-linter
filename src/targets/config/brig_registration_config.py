"""Detects user registration/account creation settings from brig ConfigMap.

Reads setRestrictUserCreation and setAllowlistEmailDomains to determine
how user accounts are created on this Wire instance. Auto-detected setting —
Julia said account creation methods are "multiple, multiple, multiple choice"
and we should detect what's configured rather than asking the user.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.yaml_parser import parse_yaml, get_nested


class BrigRegistrationConfig(BaseTarget):
    """Detect user registration mode from brig ConfigMap.

    Reads setRestrictUserCreation and setAllowlistEmailDomains to determine
    how user accounts are created.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "User registration / account creation settings"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire supports multiple account creation methods: open registration, "
            "domain-restricted registration, team invitations, SSO, and SCIM. "
            "This target detects which methods are configured in brig."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Read brig ConfigMap and detect registration settings.

        Returns:
            JSON string with registration config details.

        Raises:
            RuntimeError: If brig ConfigMap can't be fetched or parsed.
        """
        self.terminal.step("Reading brig ConfigMap for registration settings...")

        _result, cm_data = self.run_kubectl("configmap/brig")

        if not isinstance(cm_data, dict):
            raise RuntimeError("Cannot fetch brig ConfigMap")

        brig_yaml_str: str = cm_data.get("data", {}).get("brig.yaml", "")
        if not brig_yaml_str:
            raise RuntimeError("brig ConfigMap missing brig.yaml")

        try:
            brig_config: dict[str, Any] = parse_yaml(brig_yaml_str)
        except ValueError as e:
            raise RuntimeError(f"Cannot parse brig.yaml: {e}") from e

        # Extract registration settings
        restrict_user_creation: Any = get_nested(
            brig_config, "optSettings.setRestrictUserCreation", False
        )

        # setAllowlistEmailDomains can be a list of strings or null/absent
        raw_allowlist: Any = get_nested(
            brig_config, "optSettings.setAllowlistEmailDomains", None
        )
        allowlist_domains: list[str] = []
        if isinstance(raw_allowlist, list):
            allowlist_domains = [str(d) for d in raw_allowlist if d]

        result: dict[str, Any] = {
            "restrict_user_creation": bool(restrict_user_creation),
            "allowlist_email_domains": allowlist_domains,
            "has_domain_restriction": len(allowlist_domains) > 0,
        }

        # Build human-readable summary
        if restrict_user_creation:
            mode: str = "restricted (public registration disabled)"
        elif allowlist_domains:
            mode = f"domain-restricted (only {', '.join(allowlist_domains)})"
        else:
            mode = "open (anyone can register)"

        self._health_info = f"Registration mode: {mode}"
        return json.dumps(result)
