"""Checks etcd cluster health on a control plane node.

etcd is the backbone of Kubernetes if it's unhealthy, everything
breaks. Runs etcdctl cluster-health or equivalent on the first
kubenode via SSH.
"""

from __future__ import annotations

# External
import json
import re
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class EtcdHealth(BaseTarget):
    """Checks etcd cluster health.

    SSHes to the first kubenode and runs etcdctl or checks the
    etcd health endpoint to determine cluster status.
    """

    # Uses SSH to reach control plane nodes for etcd checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "etcd cluster health"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "etcd is the backbone of Kubernetes. If it is unhealthy, all API operations "
            "fail and the cluster becomes unmanageable. Healthy when endpoint reports OK."
        )

    def collect(self) -> str:
        """Check etcd cluster health on a control plane node.

        Returns:
            "healthy" if etcd is operational, "unhealthy" otherwise.

        Raises:
            RuntimeError: If no kubenodes found or etcd check fails entirely.
        """
        self.terminal.step("Checking etcd cluster health...")

        # Get the first kubenode IP
        _cmd_result, data = self.run_kubectl("nodes")
        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])
        if not items:
            raise RuntimeError("No nodes found in cluster")

        # etcd only runs on control plane nodes filter to those before picking
        # one to SSH into. Worker nodes will fail all three health commands
        # silently and return a false "unhealthy" result.
        control_plane_nodes: list[dict[str, Any]] = [
            node for node in items
            if "node-role.kubernetes.io/control-plane" in node.get("metadata", {}).get("labels", {})
            or "node-role.kubernetes.io/master" in node.get("metadata", {}).get("labels", {})
        ]
        if not control_plane_nodes:
            raise RuntimeError("No control plane nodes found in cluster")

        first_ip: str | None = None
        for addr in control_plane_nodes[0].get("status", {}).get("addresses", []):
            if addr.get("type") == "InternalIP":
                first_ip = addr.get("address")
                break

        if not first_ip:
            raise RuntimeError("Could not determine IP of first control plane node")

        # Try multiple approaches to check etcd health:
        # 1. etcdctl with auto-detected certs (v3 API)
        # 2. etcd-health.sh script if present
        # 3. Direct health endpoint via curl
        result = self.run_ssh(
            first_ip,
            "sudo ETCDCTL_API=3 etcdctl"
            " --cacert=/etc/kubernetes/pki/etcd/ca.crt"
            " --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt"
            " --key=/etc/kubernetes/pki/etcd/healthcheck-client.key"
            " endpoint health 2>/dev/null"
            " || sudo /usr/local/bin/etcd-health.sh 2>/dev/null"
            " || curl -s --cacert /etc/kubernetes/pki/etcd/ca.crt"
            " https://localhost:2379/health 2>/dev/null",
        )

        output: str = result.stdout.strip().lower()

        # etcdctl endpoint health outputs "127.0.0.1:2379 is healthy"
        # curl /health outputs {"health":"true"} (string) in etcd v3, or
        # {"health": true} (boolean) in some older versions/v2 API.
        # Try JSON parse first to handle any valid JSON formatting, then fall
        # back to regex for etcdctl text output.
        curl_healthy = False
        try:
            health_data = json.loads(result.stdout.strip())
            curl_healthy = health_data.get("health") in ("true", True)
        except (json.JSONDecodeError, AttributeError):
            pass

        if re.search(r"\bis healthy\b", output) or curl_healthy:
            self._health_info = "etcd cluster is healthy"
            return "healthy"

        self._health_info = f"etcd may be unhealthy: {result.stdout.strip()[:100]}"
        return "unhealthy"
