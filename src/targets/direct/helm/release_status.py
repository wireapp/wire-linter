"""Verify that no Helm releases are stuck in pending or failed state via kubectl.

Releases stuck in «pending-install», «pending-upgrade», or «failed» block
all future upgrades and need manual intervention to fix. This target queries
Kubernetes secrets labeled «owner=helm» instead of running «helm list» over SSH.

The raw_output mimics «helm list -A» tabular format so that
«detect_wire_server_version()» in the UI can parse it with the regex
«/wire-server-(\\d+\\.\\d+\\.\\d+)/».
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget
from src.lib.helm_helpers import decode_chart_metadata, decode_chart_version, extract_revision


class HelmReleaseStatus(BaseTarget):
    """Verify Helm releases aren't stuck in unhealthy states via kubectl.

    Queries Kubernetes secrets labeled «owner=helm» to check that all
    releases are in «deployed» state. Produces tabular raw_output compatible
    with the UI's wire-server version detection regex.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "All Helm releases in «deployed» state"

    @property
    def explanation(self) -> str:
        """Why it matters."""
        return (
            "Releases stuck in «pending-install», «pending-upgrade», or «failed» "
            "block all future upgrades and need manual intervention to resolve."
        )

    @property
    def unit(self) -> str:
        """No unit. Result is boolean."""
        return ""

    def collect(self) -> bool:
        """Verify no Helm releases are stuck in bad states.

        Queries Kubernetes secrets with label «owner=helm» across all namespaces.
        Each secret's metadata labels contain «name» (release name) and «status»
        (deployed, failed, etc.).

        Returns:
            True if all releases are in «deployed» state, False if any are stuck.

        Raises:
            RuntimeError: If no Helm release secrets are found.
        """
        self.terminal.step("Checking Helm release statuses via kubectl secrets...")

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

        # Track the latest revision per release name
        latest_by_name: dict[str, dict[str, Any]] = {}

        for item in items:
            labels: dict[str, str] = item.get("metadata", {}).get("labels", {})
            release_name: str = labels.get("name", "")

            if not release_name:
                continue

            # Extract revision from secret name: sh.helm.release.v1.<name>.v<rev>
            secret_name: str = item.get("metadata", {}).get("name", "")
            revision: int = extract_revision(secret_name)

            # Keep only the latest revision per release
            existing: dict[str, Any] | None = latest_by_name.get(release_name)
            if existing is None or revision > existing.get("revision", 0):
                latest_by_name[release_name] = {
                    "revision": revision,
                    "item": item,
                }

        # Check each release's status and build tabular output
        bad_releases: list[str] = []
        total: int = 0
        table_lines: list[str] = []

        # Header mimics «helm list -A» format
        table_lines.append("NAME\tNAMESPACE\tREVISION\tUPDATED\tSTATUS\tCHART\tAPP VERSION")

        for release_name, info in sorted(latest_by_name.items()):
            total += 1
            item: dict[str, Any] = info["item"]
            labels: dict[str, str] = item.get("metadata", {}).get("labels", {})
            status: str = labels.get("status", "unknown")
            namespace: str = item.get("metadata", {}).get("namespace", "default")
            revision: int = info["revision"]

            # Decode chart metadata from the release payload
            chart_meta: dict[str, str] = decode_chart_metadata(item)
            chart_name: str = chart_meta.get("name", "unknown")
            chart_version: str = chart_meta.get("version", "unknown")
            chart_label: str = f"{chart_name}-{chart_version}" if chart_meta else "unknown"
            app_version: str = chart_meta.get("appVersion", "")

            # The secret's creationTimestamp is the best proxy for the UPDATED column
            updated: str = item.get("metadata", {}).get("creationTimestamp", "")

            # Build a table line matching «helm list -A» format for UI parsing
            # The UI regex looks for «wire-server-(\d+\.\d+\.\d+)» in the chart column
            table_lines.append(
                f"{release_name}\t{namespace}\t{revision}\t"
                f"{updated}\t{status}\t{chart_label}\t{app_version}"
            )

            if status != "deployed":
                bad_releases.append(f"{release_name} ({status})")

        # Clear the JSON output auto-tracked by run_kubectl — we only want the
        # human-readable tabular format that the UI parses for wire-server version
        self._raw_outputs = []

        # Store the tabular output so the UI can parse wire-server version
        raw_table: str = "\n".join(table_lines)
        self._track_output("kubectl get secrets -l owner=helm", raw_table)

        all_ok: bool = len(bad_releases) == 0

        if all_ok:
            self._health_info = f"All {total} releases deployed"
        else:
            self._health_info = f"{len(bad_releases)} stuck/failed: {', '.join(bad_releases)}"

        return all_ok
