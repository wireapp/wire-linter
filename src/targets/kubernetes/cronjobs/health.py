"""Fetches CronJob status and last run results from the Wire namespace.

CronJobs handle periodic tasks like backups and certificate rotation.
A silently failing CronJob can go unnoticed for weeks until the backup
is needed or a certificate expires.

Produces a single data point at « kubernetes/cronjobs/health ».
Value is a JSON string with CronJob details and last run status.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class CronJobHealth(BaseTarget):
    """Fetches CronJob configuration and last run status.

    Queries all CronJobs in the Wire namespace, then correlates with
    Jobs to determine the status of the most recent run.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "CronJob health and last run status"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "CronJobs handle periodic tasks like backups and certificate rotation. "
            "A silently failing CronJob can go unnoticed until the backup is needed "
            "or the certificate expires."
        )

    def collect(self) -> str:
        """Fetch CronJobs and their most recent Job status.

        Returns:
            JSON string with CronJob details including last run status.
        """
        namespace: str = self.config.cluster.kubernetes_namespace

        self.terminal.step("Fetching CronJobs...")

        _result, cronjobs_parsed = self.run_kubectl(
            "cronjobs", namespace=namespace
        )

        self.terminal.step("Fetching Jobs for correlation...")

        _result_jobs, jobs_parsed = self.run_kubectl(
            "jobs", namespace=namespace
        )

        # Build a map of CronJob name -> most recent Job
        cronjob_last_job: dict[str, dict[str, Any]] = {}

        if isinstance(jobs_parsed, dict):
            for job in jobs_parsed.get("items", []):
                # Find the owning CronJob via ownerReferences
                owner_refs: list[dict[str, Any]] = (
                    job.get("metadata", {}).get("ownerReferences", [])
                )
                for ref in owner_refs:
                    if ref.get("kind") == "CronJob":
                        cj_name: str = ref.get("name", "")
                        # Keep the most recent job (by creation timestamp)
                        job_created: str = (
                            job.get("metadata", {}).get("creationTimestamp", "")
                        )
                        existing: dict[str, Any] | None = cronjob_last_job.get(cj_name)
                        if (
                            existing is None
                            or job_created > existing.get("created", "")
                        ):
                            # Determine job status
                            job_status: dict[str, Any] = job.get("status", {})
                            succeeded: int = job_status.get("succeeded", 0) or 0
                            failed: int = job_status.get("failed", 0) or 0
                            active: int = job_status.get("active", 0) or 0

                            if succeeded > 0:
                                status_str: str = "succeeded"
                            elif failed > 0:
                                status_str = "failed"
                            elif active > 0:
                                status_str = "running"
                            else:
                                status_str = "unknown"

                            cronjob_last_job[cj_name] = {
                                "name": job.get("metadata", {}).get("name", ""),
                                "created": job_created,
                                "status": status_str,
                                "completion_time": job_status.get("completionTime"),
                            }

        # Process CronJobs
        cronjobs: list[dict[str, Any]] = []

        if isinstance(cronjobs_parsed, dict):
            for item in cronjobs_parsed.get("items", []):
                cj_name = item.get("metadata", {}).get("name", "")
                cj_spec: dict[str, Any] = item.get("spec", {})
                cj_status: dict[str, Any] = item.get("status", {})

                last_schedule: str | None = cj_status.get("lastScheduleTime")
                active_jobs: int = len(cj_status.get("active", []))

                # Find last job status
                last_job: dict[str, Any] | None = cronjob_last_job.get(cj_name)

                cronjobs.append({
                    "name": cj_name,
                    "schedule": cj_spec.get("schedule", ""),
                    "suspended": cj_spec.get("suspend", False),
                    "last_schedule": last_schedule,
                    "active_jobs": active_jobs,
                    "last_job_status": last_job["status"] if last_job else None,
                    "last_job_name": last_job["name"] if last_job else None,
                    "last_job_completion": (
                        last_job["completion_time"] if last_job else None
                    ),
                })

        cronjob_count: int = len(cronjobs)
        failed_count: int = sum(
            1 for cj in cronjobs if cj.get("last_job_status") == "failed"
        )

        if cronjob_count == 0:
            self._health_info = "No CronJobs found"
        elif failed_count > 0:
            self._health_info = f"{failed_count}/{cronjob_count} CronJob(s) last run failed"
        else:
            self._health_info = f"{cronjob_count} CronJob(s), all OK"

        return json.dumps({
            "cronjob_count": cronjob_count,
            "cronjobs": cronjobs,
        }, sort_keys=True)
