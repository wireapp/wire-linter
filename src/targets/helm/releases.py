"""Lists all Helm releases with their chart versions.

We run «helm list -A -o json» to see what chart versions are deployed across
the cluster. This is useful for support cases and checking if versions stay
consistent and up to date. «Helm» runs inside the wire-server-deploy Docker
container alongside kubectl.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget


class HelmReleases(BaseTarget):
    """Lists all «Helm» releases deployed in the cluster.

    We run «helm list» through the same SSH/Docker setup as kubectl to grab
    all releases, their chart names, and versions.
    """

    # Uses SSH to admin host for helm commands
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What we're collecting."""
        return "Helm chart releases and versions"

    @property
    def explanation(self) -> str:
        """Why we need this."""
        return (
            "Captures which «Helm» charts are running and what versions. "
            "Useful for support investigations and spotting version drift across services."
        )

    def collect(self) -> str:
        """Run «helm list -A -o json» and parse the releases.

        We grab «JSON» output instead of parsing tables since column positions
        shift across different «helm» versions.

        Returns:
            Comma-separated list of «name=chart (status)» entries.

        Raises:
            RuntimeError: If «helm list» fails or returns nothing.
        """
        self.terminal.step("Listing Helm releases...")

        # «Helm» isn't a kubectl resource, so we run it separately via SSH.
        # The wire-server-deploy Docker container is where «helm» lives on
        # managed Wire deployments, so we prefer that if available.
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

        # Parse the «JSON» output from «helm list»
        try:
            entries: list[dict[str, str]] = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"«helm list» gave us bad «JSON»: {exc}") from exc

        releases: list[str] = []
        for entry in entries:
            name: str   = entry.get("name", "?")
            chart: str  = entry.get("chart", "?")
            status: str = entry.get("status", "?")
            releases.append(f"{name}={chart} ({status})")

        self._health_info = f"{len(releases)} Helm release(s)"
        return ", ".join(releases) if releases else output[:200]
