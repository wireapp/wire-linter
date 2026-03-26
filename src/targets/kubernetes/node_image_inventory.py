"""Inventories container images on each Kubernetes node.

For Wire-managed (kubespray) clusters without an image registry, images are
pre-loaded onto each node. If containerd garbage-collects an image from one
node but not others, rescheduled pods will hit ImagePullBackOff.

This target SSHes into each kubenode and lists images present, then reports
any images that exist on some nodes but not all.
"""

from __future__ import annotations

# External
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class NodeImageInventory(BaseTarget):
    """Inventory container images across kubenodes for consistency.

    Only runs when wire_managed_cluster is true (non-Wire-managed clusters
    have image registries, so this check is irrelevant). Requires SSH.
    """

    # Needs SSH to reach kubenodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Container image inventory across kubenodes"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "In Wire-managed offline clusters without an image registry, container "
            "images are pre-loaded onto each node. If a node evicts an image due to "
            "disk pressure, pods rescheduled to that node will fail. This check "
            "compares image lists across nodes to find inconsistencies."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """SSH into each kubenode and list container images.

        Returns:
            JSON string with per-node image lists and inconsistencies.

        Raises:
            NotApplicableError: If cluster is not Wire-managed.
        """
        if not self.config.options.wire_managed_cluster:
            raise NotApplicableError("Not a Wire-managed cluster (image registry expected)")

        self.terminal.step("Inventorying container images across kubenodes...")

        # Get the list of kubenode IPs
        kube_nodes: list[str] = self.config.nodes.kube_nodes
        if not kube_nodes:
            # Try to discover nodes from kubectl
            try:
                _result, nodes_data = self.run_kubectl("nodes")
                if isinstance(nodes_data, dict):
                    for item in nodes_data.get("items", []):
                        addresses: list[dict[str, str]] = item.get("status", {}).get("addresses", [])
                        for addr in addresses:
                            if addr.get("type") == "InternalIP":
                                kube_nodes.append(addr["address"])
            except RuntimeError:
                pass

        if not kube_nodes:
            raise RuntimeError("No kubenodes found to inventory images on")

        # Collect images from each node
        node_images: dict[str, list[str]] = {}
        all_images: set[str] = set()

        for node_ip in kube_nodes[:6]:
            self.terminal.step(f"  Listing images on {node_ip}...")
            try:
                # Try crictl first (standard containerd tool)
                result, _parsed = self.run_command_on_host(
                    node_ip,
                    "crictl images -q 2>/dev/null || ctr -n k8s.io images list -q 2>/dev/null || echo '__UNAVAILABLE__'"
                )
                output: str = result.stdout.strip() if result else ""

                if "__UNAVAILABLE__" in output or not output:
                    node_images[node_ip] = []
                    continue

                # Parse image list (one image ref per line)
                images: list[str] = [
                    line.strip() for line in output.split("\n")
                    if line.strip() and not line.startswith("sha256:")
                ]
                node_images[node_ip] = images
                all_images.update(images)
            except RuntimeError:
                node_images[node_ip] = []

        # Find inconsistencies: images present on some nodes but not all
        inconsistent: list[dict[str, Any]] = []
        for image in sorted(all_images):
            present_on: list[str] = [ip for ip, imgs in node_images.items() if image in imgs]
            missing_on: list[str] = [ip for ip, imgs in node_images.items() if image not in imgs and len(imgs) > 0]

            # Only flag if at least one node has it and at least one doesn't
            if present_on and missing_on:
                inconsistent.append({
                    "image": image,
                    "present_on": present_on,
                    "missing_on": missing_on,
                })

        result_data: dict[str, Any] = {
            "nodes": [
                {"name": ip, "image_count": len(imgs)}
                for ip, imgs in node_images.items()
            ],
            "total_unique_images": len(all_images),
            "inconsistent_images": inconsistent[:20],
            "inconsistent_count": len(inconsistent),
        }

        if not inconsistent:
            self._health_info = f"All images consistent across {len(node_images)} nodes ({len(all_images)} unique images)"
        else:
            self._health_info = f"{len(inconsistent)} image(s) inconsistent across nodes"

        return json.dumps(result_data)
