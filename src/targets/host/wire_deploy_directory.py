"""Checks for the wire-server-deploy directory on the admin host.

In Wire-managed clusters, the admin host has ~/wire-server-deploy/ with
ansible playbooks, helm values, and deployment artifacts. If the cluster
is Wire-managed but this directory is missing, something's wrong.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class WireDeployDirectory(BaseTarget):
    """Check for wire-server-deploy directory on the admin host.

    Only runs when wire_managed_cluster is true.
    """

    # Needs SSH access to the admin host
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Wire-server-deploy directory on admin host"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Wire-managed clusters use the wire-server-deploy repository on the admin "
            "host for deployment. It contains ansible playbooks, helm values, inventory "
            "files, and deployment scripts."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Check for wire-server-deploy directory and list contents.

        Returns:
            JSON string with directory existence and contents.

        Raises:
            NotApplicableError: If cluster is not Wire-managed.
        """
        if not self.config.options.wire_managed_cluster:
            raise NotApplicableError("Cluster is not Wire-managed (no ansible layer expected)")

        self.terminal.step("Checking for wire-server-deploy directory on admin host...")

        # Check if the directory exists and list top-level contents
        result_str, _parsed = self.run_command_on_host(
            self.config.admin_host.ip,
            "ls -1 ~/wire-server-deploy/ 2>/dev/null || echo '__NOT_FOUND__'"
        )

        output: str = result_str.stdout.strip() if result_str else ""

        if "__NOT_FOUND__" in output or not output:
            result: dict[str, Any] = {
                "exists": False,
                "subdirectories": [],
                "inventory_dirs": [],
            }
            self._health_info = "wire-server-deploy directory NOT found on admin host"
            return json.dumps(result)

        # Parse directory listing
        subdirectories: list[str] = [line.strip() for line in output.split("\n") if line.strip()]

        # Check for inventory directories
        inv_result_str, _parsed2 = self.run_command_on_host(
            self.config.admin_host.ip,
            "ls -1 ~/wire-server-deploy/ansible/inventory/ 2>/dev/null || echo ''"
        )
        inv_output: str = inv_result_str.stdout.strip() if inv_result_str else ""
        inventory_dirs: list[str] = [d.strip() for d in inv_output.split("\n") if d.strip()]

        result = {
            "exists": True,
            "subdirectories": subdirectories,
            "inventory_dirs": inventory_dirs,
        }

        self._health_info = (
            f"wire-server-deploy found: {len(subdirectories)} items, "
            f"inventory: {', '.join(inventory_dirs) if inventory_dirs else 'none'}"
        )

        return json.dumps(result)
