"""Checks that schema/data migration jobs have completed.

A failed migration job breaks services. We verify cassandra-migrations,
elasticsearch-index-create, and service-specific migrate-data jobs all
finished running.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Patterns to match migration job names
_MIGRATION_JOB_PATTERNS: list[str] = [
    "cassandra-migrations",
    "elasticsearch-index",
    "brig-index",
    "galley-migrate",
    "spar-migrate",
    "gundeck-migrate",
]


class MigrationJobsCompleted(BaseTarget):
    """Checks that migration jobs have completed.

    Queries the Wire namespace for jobs and verifies all migration-related
    jobs finished.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "Schema/data migration jobs completed"

    @property
    def explanation(self) -> str:
        """Why this matters and what healthy looks like."""
        return (
            "Failed migrations break services with schema mismatches. "
            "Healthy means all cassandra-migrations, elasticsearch-index, and "
            "service migrate-data jobs succeeded."
        )

    @property
    def unit(self) -> str:
        """No unit just a pass/fail check."""
        return ""

    def collect(self) -> bool:
        """Check if all migration jobs completed.

        Returns True if done, False if any are incomplete or failed.
        """
        self.terminal.step("Checking migration job status...")

        cmd_result, data = self.run_kubectl("jobs")

        if data is None:
            raise RuntimeError("Failed to query jobs from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])

        # Find jobs matching our migration patterns
        migration_jobs: list[dict[str, Any]] = []
        for item in items:
            name: str = item.get("metadata", {}).get("name", "")
            for pattern in _MIGRATION_JOB_PATTERNS:
                if pattern in name:
                    migration_jobs.append(item)
                    break

        if not migration_jobs:
            self._health_info = "No migration jobs found"
            return True

        completed: list[str] = []
        incomplete: list[str] = []

        for job in migration_jobs:
            name: str = job.get("metadata", {}).get("name", "unknown")
            status: dict[str, Any] = job.get("status", {})

            # Job is done if it succeeded at least once
            succeeded: int = status.get("succeeded", 0) or 0
            failed: int = status.get("failed", 0) or 0

            if succeeded >= 1:
                completed.append(name)
            elif failed > 0:
                incomplete.append(f"{name} (failed)")
            else:
                incomplete.append(f"{name} (not completed)")

        all_done: bool = len(incomplete) == 0

        if all_done:
            self._health_info = f"All {len(completed)} migration jobs completed"
        else:
            self._health_info = f"Incomplete: {', '.join(incomplete)}"

        return all_done
