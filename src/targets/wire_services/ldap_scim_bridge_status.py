"""Detects LDAP-SCIM bridge CronJobs and reports their status.

Julia said: "The LDAP SCIM bridge is a Kubernetes cron job. You won't always see
it running, but you will see the cron job." It's deployed one per team that is
being synchronized from LDAP/Active Directory.

This target always runs (the bridge is not "enabled" anywhere — it's either
deployed or not). We just look for what's there and report it.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class LdapScimBridgeStatus(BaseTarget):
    """Detect LDAP-SCIM bridge CronJobs and report their status.

    Searches for CronJobs matching ldap-scim-bridge*. Reports existence,
    schedule, and last run status for each.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "LDAP-SCIM bridge CronJob status"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The LDAP-SCIM bridge synchronizes users from Active Directory or LDAP "
            "into Wire via the SCIM API. It runs as a Kubernetes CronJob (one per team). "
            "If the bridge is deployed but failing, user synchronization stops."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Search for ldap-scim-bridge CronJobs and report their status.

        Returns:
            JSON string with CronJob details.
        """
        self.terminal.step("Searching for LDAP-SCIM bridge CronJobs...")

        # Get all CronJobs in the namespace
        _result, data = self.run_kubectl("cronjobs")

        if not isinstance(data, dict):
            raise RuntimeError("Cannot fetch CronJob list")

        items: list[dict[str, Any]] = data.get("items", [])
        bridge_cronjobs: list[dict[str, Any]] = []

        for cj in items:
            name: str = cj.get("metadata", {}).get("name", "")
            # Match CronJobs that look like LDAP-SCIM bridge deployments
            if "ldap-scim-bridge" in name.lower() or "ldap-scim" in name.lower():
                spec: dict[str, Any] = cj.get("spec", {})
                status: dict[str, Any] = cj.get("status", {})

                schedule: str = spec.get("schedule", "")
                last_schedule_time: str = str(status.get("lastScheduleTime", ""))
                active_jobs: int = len(status.get("active", []))

                # Try to determine last job success by checking lastSuccessfulTime
                last_successful_time: str = str(status.get("lastSuccessfulTime", ""))

                bridge_cronjobs.append({
                    "name": name,
                    "schedule": schedule,
                    "last_schedule_time": last_schedule_time,
                    "last_successful_time": last_successful_time,
                    "active_jobs": active_jobs,
                    # If lastSuccessfulTime >= lastScheduleTime, last run succeeded
                    "last_job_succeeded": (
                        last_successful_time >= last_schedule_time
                        if last_successful_time and last_schedule_time
                        else None
                    ),
                })

        result: dict[str, Any] = {
            "cronjobs_found": len(bridge_cronjobs),
            "cronjobs": bridge_cronjobs,
        }

        if not bridge_cronjobs:
            self._health_info = "No LDAP-SCIM bridge CronJobs found in the cluster"
        else:
            names: str = ", ".join(cj["name"] for cj in bridge_cronjobs)
            self._health_info = f"{len(bridge_cronjobs)} LDAP-SCIM bridge(s) found: {names}"

        return json.dumps(result)
