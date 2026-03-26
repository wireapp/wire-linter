"""Checks the OS version on all VMs against Wire's supported versions.

Connects to each VM via SSH and reads /etc/os-release. Wire tests on
Ubuntu 18.04, 22.04, and 24.04 — other versions might cause subtle issues
with dependencies or kernel features.
"""

from __future__ import annotations

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


class OsVersion(PerHostTarget):
    """Checks OS version on each VM.

    Discovers VMs via kubectl and config, reads /etc/os-release on each,
    and reports the distribution and version.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "OS version on each host"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Wire tests on Ubuntu 18.04, 22.04, and 24.04. Other versions can "
            "cause subtle issues with dependencies or kernel stuff."
        )

    def get_hosts(self) -> list[dict[str, str]]:
        """Return the list of VM hosts to check.

        Returns:
            List of host dicts with 'name' and 'ip' keys.
        """
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> str:
        """SSH into host and read the OS version from /etc/os-release.

        Args:
            host: Dict with 'name' and 'ip' keys identifying the target VM.

        Returns:
            OS version string like "Ubuntu 24.04.1 LTS".

        Raises:
            RuntimeError: If /etc/os-release cannot be parsed.
        """
        self.terminal.step(f"Checking OS version on {host['name']}...")

        # /etc/os-release exists on all modern distros
        result = self.run_ssh(host["ip"], "cat /etc/os-release")

        # Extract PRETTY_NAME for the human version and VERSION_ID for checking
        pretty_name: str = ""
        version_id: str = ""

        for line in result.stdout.strip().split("\n"):
            if line.startswith("PRETTY_NAME="):
                # Strip the key and quotes
                pretty_name = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("VERSION_ID="):
                version_id = line.split("=", 1)[1].strip().strip('"')

        if not pretty_name:
            raise RuntimeError(f"Could not parse /etc/os-release on {host['name']}")

        # Check against Wire's supported versions
        supported_versions: list[str] = ["18.04", "22.04", "24.04"]
        is_supported: bool = version_id in supported_versions

        # Report whether the version is supported
        if is_supported:
            self._health_info = f"{pretty_name} (supported)"
        else:
            self._health_info = f"{pretty_name} (not tested with Wire, needs: {', '.join(supported_versions)})"

        return pretty_name

    def description_for_host(self, host: dict[str, str]) -> str:
        """Return a per-host label for display in results.

        Args:
            host: Dict with 'name' and 'ip' keys.

        Returns:
            Human-readable string identifying this host's measurement.
        """
        return f"OS version on {host['name']} ({host['ip']})"
