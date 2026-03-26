"""Checks that IS_SELF_HOSTED flag is set in team-settings and account-pages.

Without it, team-settings shows « wire for free » prompts and payment UI
that doesn't work on-prem.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class IsSelfHosted(BaseTarget):
    """Checks IS_SELF_HOSTED flag in team-settings and account-pages.

    Fetches both deployments and checks their env vars for the
    IS_SELF_HOSTED flag.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "IS_SELF_HOSTED flag set in team-settings and account-pages"

    @property
    def explanation(self) -> str:
        """Why we're checking and what's healthy vs unhealthy."""
        return (
            "Without IS_SELF_HOSTED=true, team-settings shows « wire for free » prompts "
            "and payment UI that doesn't work on-prem. It's healthy when both services have it set."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty, result is boolean)."""
        return ""

    def collect(self) -> bool:
        """Check for IS_SELF_HOSTED flag in both services.

        Returns:
            True if both have IS_SELF_HOSTED=true, False otherwise.
        """
        self.terminal.step("Checking IS_SELF_HOSTED flag...")

        services: list[str] = ["team-settings", "account-pages"]
        results: dict[str, bool] = {}

        for svc in services:
            _result, deploy_data = self.run_kubectl(f"deployment/{svc}")

            is_set: bool = False

            if isinstance(deploy_data, dict):
                containers: list[dict[str, Any]] = (
                    deploy_data.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("containers", [])
                )

                for container in containers:
                    for env in container.get("env", []):
                        if env.get("name") == "IS_SELF_HOSTED":
                            env_value: str = str(env.get("value", "")).lower()
                            is_set = env_value in ("true", "1", "yes")
                            break
                    else:
                        # Inner loop exhausted without finding the flag, keep checking containers
                        continue
                    # Inner loop broke (flag found), stop checking further containers
                    break

            results[svc] = is_set

        all_set: bool = all(results.values())

        if all_set:
            self._health_info = "IS_SELF_HOSTED=true in both services"
        else:
            missing: list[str] = [svc for svc, is_set in results.items() if not is_set]
            self._health_info = f"IS_SELF_HOSTED not set in: {', '.join(missing)}"

        return all_set
