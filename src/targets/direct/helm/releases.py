"""Lists all Helm releases with their chart versions via kubectl.

Helm stores each release as a Kubernetes secret with the label «owner=helm».
Instead of running «helm list» over SSH, we query these secrets directly via
kubectl and decode the embedded release metadata to extract chart names and
versions. This avoids the need for SSH access to the admin host.

The secret name follows the pattern «sh.helm.release.v1.<name>.v<revision>».
The «.data.release» field is base64-encoded, gzip-compressed JSON containing
the full release info including chart name and version.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.helm_helpers import decode_chart_version, extract_revision


class HelmReleases(BaseTarget):
    """Lists all Helm releases deployed in the cluster via kubectl secrets.

    Queries Kubernetes secrets labeled «owner=helm» across all namespaces,
    then decodes each secret's release payload to extract the chart name,
    version, and deployment status.
    """

    @property
    def description(self) -> str:
        """What we're collecting."""
        return "Helm chart releases and versions"

    @property
    def explanation(self) -> str:
        """Why we need this."""
        return (
            "Captures which Helm charts are running and what versions. "
            "Useful for support investigations and spotting version drift across services."
        )

    def collect(self) -> str:
        """Query kubectl for Helm release secrets and decode chart versions.

        Each Helm release is stored as a Kubernetes secret with label «owner=helm».
        The secret's «.data.release» field contains base64+gzip-compressed JSON
        with the full release metadata.

        Returns:
            Comma-separated list of «name=chart-version (status)» entries.

        Raises:
            RuntimeError: If no Helm release secrets are found.
        """
        self.terminal.step("Listing Helm releases via kubectl secrets...")

        # Helm release secrets are labeled «owner=helm» across all namespaces
        cmd_result, data = self.run_kubectl(
            "secrets",
            selector="owner=helm",
            all_namespaces=True,
        )

        if data is None:
            raise RuntimeError("Could not query Helm release secrets from Kubernetes")

        items: list[dict[str, Any]] = data.get("items", [])

        if not items:
            raise RuntimeError("No Helm release secrets found in any namespace")

        # Track the latest revision per release name so we report only the current one
        latest_by_name: dict[str, dict[str, Any]] = {}

        for item in items:
            labels: dict[str, str] = item.get("metadata", {}).get("labels", {})
            release_name: str = labels.get("name", "")
            release_status: str = labels.get("status", "unknown")

            if not release_name:
                continue

            # Extract revision from the secret name pattern: sh.helm.release.v1.<name>.v<rev>
            secret_name: str = item.get("metadata", {}).get("name", "")
            revision: int = extract_revision(secret_name)

            # Keep only the latest revision per release
            existing: dict[str, Any] | None = latest_by_name.get(release_name)
            if existing is None or revision > existing.get("revision", 0):
                latest_by_name[release_name] = {
                    "revision": revision,
                    "status": release_status,
                    "item": item,
                }

        # Decode each release's chart name and version from the compressed payload
        releases: list[str] = []

        for release_name, info in sorted(latest_by_name.items()):
            chart_label: str = decode_chart_version(info["item"])
            status: str = info["status"]
            releases.append(f"{release_name}={chart_label} ({status})")

        self._health_info = f"{len(releases)} Helm release(s)"
        return ", ".join(releases) if releases else "no releases found"
