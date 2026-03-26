"""Verify that no Helm releases are stuck in pending or failed state.

Releases stuck in «pending-install», «pending-upgrade», or «failed» block
all future upgrades and need manual intervention to fix.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget


class HelmReleaseStatus(BaseTarget):
    """Verify Helm releases aren't stuck in unhealthy states.

    Runs «helm list -A -o json» to check for releases in «pending-install»,
    «pending-upgrade», or «failed» state. Uses JSON output to avoid fragile
    text-table parsing where the UPDATED column contains spaces.
    """

    # Uses SSH to admin host for helm commands
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        return "All Helm releases in «deployed» state"

    @property
    def explanation(self) -> str:
        return (
            "Releases stuck in «pending-install», «pending-upgrade», or «failed» "
            "block all future upgrades and need manual intervention to resolve."
        )

    @property
    def unit(self) -> str:
        return ""

    def collect(self) -> bool:
        """Verify no Helm releases are stuck in bad states.

        Returns:
            True if all releases are in «deployed» state, False if any are stuck.

        Raises:
            RuntimeError: If «helm list» cannot be executed or returns bad JSON.
        """
        self.terminal.step("Checking Helm release statuses...")

        # Use SSH/Docker to run helm list with JSON output to avoid fragile
        # text-table parsing (the UPDATED column contains spaces that break
        # whitespace-split fallback).
        # Always resolve the Docker image regardless of SSH routing — helm
        # lives inside the wire-server-deploy container even when running
        # locally on the admin host (run_ssh handles local execution internally)
        docker_image: str = self._resolve_kubectl_docker_image()

        if docker_image:
            # Run inside the wire-server-deploy container
            result = self.run_ssh(
                self.config.admin_host.ip,
                f"docker run --rm --network=host"
                f" -v {self.config.kubernetes.admin_home}/.ssh:/root/.ssh"
                f" -v {self.config.kubernetes.admin_home}/wire-server-deploy:/wire-server-deploy"
                f" {docker_image} helm list -A -o json 2>/dev/null",
            )
        else:
            # Fall back to running helm directly on the host
            result = self.run_ssh(
                self.config.admin_host.ip,
                "helm list -A -o json 2>/dev/null",
            )

        output: str = result.stdout.strip()
        if not output:
            raise RuntimeError("helm list returned no output")

        # Parse the JSON output from «helm list»
        try:
            entries: list[dict[str, str]] = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"helm list returned invalid JSON: {exc}") from exc

        # Find any releases that aren't in deployed state
        bad_releases: list[str] = []

        for entry in entries:
            name: str = entry.get("name", "?")
            status: str = entry.get("status", "?").lower()

            if status != "deployed":
                bad_releases.append(f"{name} ({status})")

        total: int = len(entries)
        all_ok: bool = len(bad_releases) == 0

        if all_ok:
            self._health_info = f"All {total} releases deployed"
        else:
            self._health_info = f"{len(bad_releases)} stuck/failed: {', '.join(bad_releases)}"

        return all_ok
