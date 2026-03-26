"""Checks backup freshness for Cassandra snapshots and MinIO backups.

Old backups usually mean the backup job died silently. We look for
recent backup files and check their timestamps.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class BackupFreshness(BaseTarget):
    """Checks backup freshness.

    Logs into the admin host over SSH and hunts for recent backup files
    to see if the backup jobs are actually working.
    """

    # Uses SSH to admin host for backup file checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Backup freshness (last backup age)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Old or missing backups = the backup job probably died. "
            "We're good if we see recent files (less than 1 hour old)."
        )

    def collect(self) -> str:
        """Check how old the most recent backups are.

        Returns:
            Short summary of what we found.
        """
        self.terminal.step("Checking backup freshness...")

        # Loop through common backup directories, listing the first one that
        # exists AND has actual files. tail -n +2 strips ls's "total N" header,
        # and [ -n "$files" ] ensures we skip empty directories instead of
        # short-circuiting on head's always-0 exit code.
        result = self.run_ssh(
            self.config.admin_host.ip,
            "for d in /var/backups/cassandra ~/backups /mnt/backups; do"
            " [ -d \"$d\" ] && files=$(ls -lt \"$d\" 2>/dev/null | tail -n +2 | head -3)"
            " && [ -n \"$files\" ] && echo \"$files\" && exit 0;"
            " done; echo 'NO_BACKUPS_FOUND'",
        )

        output: str = result.stdout.strip()

        if "NO_BACKUPS_FOUND" in output:
            # Try to find backup directories
            find_result = self.run_ssh(
                self.config.admin_host.ip,
                "find / -maxdepth 3 -name '*backup*' -type d 2>/dev/null | head -5",
            )

            if find_result.stdout.strip():
                self._health_info = f"Backup directories found but couldn't list: {find_result.stdout.strip()}"
                return "backup dirs found, check manually"

            self._health_info = "No backup files or directories found"
            return "no backups found"

        # Try to figure out how old the most recent backup is. Only search
        # directories that actually exist to avoid spurious find errors.
        # -print -quit stops after the first match (faster), and grep -q .
        # checks if we actually found anything (head -1 always succeeds).
        age_result = self.run_ssh(
            self.config.admin_host.ip,
            "dirs=''; for d in /var/backups/cassandra ~/backups /mnt/backups; do"
            " [ -d \"$d\" ] && dirs=\"$dirs $d\"; done;"
            " [ -z \"$dirs\" ] && echo 'OLD_OR_MISSING' && exit 0;"
            # $dirs is intentionally unquoted: find needs each path as a
            # separate argument, and the paths are hardcoded without spaces.
            " find $dirs -maxdepth 2 -type f -mmin -60 -print -quit 2>/dev/null"
            " | grep -q . && echo 'RECENT' || echo 'OLD_OR_MISSING'",
        )

        if "RECENT" in age_result.stdout:
            self._health_info = "Recent backup files found (< 1 hour old)"
            return "recent (< 1h)"
        else:
            self._health_info = "No backup files newer than 1 hour found"
            return "old or missing"
