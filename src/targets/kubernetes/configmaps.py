"""Fetches rendered configuration for all Wire services and their infrastructure
from Kubernetes ConfigMaps.

Wire services read a YAML config file at startup. That file gets rendered from
Helm values and dropped into a ConfigMap. Extracting these ConfigMaps tells you
exactly how the deployment is configured, period. No guessing.

Produces one data point per service with the raw ConfigMap content.
Paths are « kubernetes/configmaps/<service> ».

Services collected:
    Wire core:       brig, galley, gundeck, cannon, cargohold, spar,
                     nginz, background-worker
    Infrastructure:  coturn, sftd, turn, smallstep
    k8s system:      etcd (via kubeadm-config in kube-system)
"""

from __future__ import annotations

from typing import Any

# Ours
from src.lib.per_configmap_target import PerConfigmapTarget, ConfigmapSpec


# List of all ConfigMaps to collect, in the order they'll be displayed.
# name shows up in the path as « kubernetes/configmaps/<name> »
# configmap_name the actual Kubernetes ConfigMap object name
# namespace None means use whatever namespace is in the runner config (usually « default »)
# data_key which key to pull from .data. None means grab the first one available
# description what to call this in the UI
_CONFIGMAP_SPECS: list[ConfigmapSpec] = [
    # ── Wire core services ────────────────────────────────────────────────
    {
        "name":           "brig",
        "configmap_name": "brig",
        "namespace":      None,
        "data_key":       "brig.yaml",
        "description":    "Brig (user accounts) rendered configuration",
    },
    {
        "name":           "galley",
        "configmap_name": "galley",
        "namespace":      None,
        "data_key":       "galley.yaml",
        "description":    "Galley (conversations) rendered configuration",
    },
    {
        "name":           "gundeck",
        "configmap_name": "gundeck",
        "namespace":      None,
        "data_key":       "gundeck.yaml",
        "description":    "Gundeck (push notifications) rendered configuration",
    },
    {
        "name":           "cannon",
        "configmap_name": "cannon",
        "namespace":      None,
        "data_key":       "cannon.yaml",
        "description":    "Cannon (WebSocket push) rendered configuration",
    },
    {
        "name":           "cargohold",
        "configmap_name": "cargohold",
        "namespace":      None,
        "data_key":       "cargohold.yaml",
        "description":    "Cargohold (asset storage) rendered configuration",
    },
    {
        "name":           "spar",
        "configmap_name": "spar",
        "namespace":      None,
        "data_key":       "spar.yaml",
        "description":    "Spar (SSO / SAML / SCIM) rendered configuration",
    },
    {
        "name":           "nginz",
        "configmap_name": "nginz",
        "namespace":      None,
        "data_key":       "nginx.conf",
        "description":    "Nginz (API gateway) rendered nginx configuration",
    },
    {
        "name":           "background-worker",
        "configmap_name": "background-worker",
        "namespace":      None,
        "data_key":       "background-worker.yaml",
        "description":    "Background Worker rendered configuration",
    },
    # ── Supporting infrastructure ─────────────────────────────────────────
    {
        "name":           "coturn",
        "configmap_name": "coturn",
        "namespace":      None,
        "data_key":       "coturn.conf.template",
        "description":    "Coturn (TURN server) rendered configuration template",
    },
    {
        "name":           "sftd",
        "configmap_name": "sftd-join-call",
        "namespace":      None,
        "data_key":       "default.conf.template",
        "description":    "SFTd (SFT gateway) rendered nginx configuration template",
    },
    {
        "name":           "turn",
        "configmap_name": "turn",
        "namespace":      None,
        "data_key":       "turn-servers-v2.txt",
        "description":    "TURN server address list (v2 format)",
    },
    {
        "name":           "smallstep",
        "configmap_name": "smallstep-step-certificates-config",
        "namespace":      None,
        "data_key":       "ca.json",
        "description":    "Smallstep CA (MLS certificate authority) configuration",
    },
    # ── Kubernetes system ─────────────────────────────────────────────────
    {
        "name":           "etcd",
        "configmap_name": "kubeadm-config",
        "namespace":      "kube-system",
        "data_key":       "ClusterConfiguration",
        "description":    "Kubernetes cluster configuration including etcd settings",
    },
]


class KubernetesConfigmaps(PerConfigmapTarget):
    """Fetches rendered configuration for all Wire services and k8s infrastructure.

    Each Wire service reads its config from a ConfigMap when it starts up.
    This target pulls those ConfigMaps so you can validate settings, check
    for placeholder values, and cross-reference between services.

    Produces one data point per service at « kubernetes/configmaps/<service> ».
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Kubernetes ConfigMap configuration for Wire services and infrastructure"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Wire services load their config from ConfigMaps at startup. We pull these "
            "so we can validate settings, find placeholders, and make sure values line up across services."
        )

    def get_configmaps(self) -> list[ConfigmapSpec]:
        """Return the list of ConfigMaps to collect.

        Returns:
            The static list of all Wire service and infrastructure ConfigMap specs.
        """
        # Specs live at module level so they're easy to inspect and extend
        # without fiddling with the class itself
        return _CONFIGMAP_SPECS

    def collect_for_configmap(self, spec: ConfigmapSpec) -> str | None:
        """Fetch the content of a single ConfigMap from Kubernetes.

        Runs kubectl to get the ConfigMap as JSON, then pulls out the requested
        data key. If you didn't specify a key, grabs the first one it finds.

        Args:
            spec: The ConfigmapSpec describing which ConfigMap to fetch.

        Returns:
            The content string of the requested data key, or None if the
            ConfigMap exists but the key isn't there.

        Raises:
            RuntimeError: If the ConfigMap doesn't exist or kubectl fails.
        """
        # Figure out the namespace. Use the spec's override if it exists,
        # otherwise fall back to whatever the runner config says
        namespace: str = spec.get("namespace") or self.config.cluster.kubernetes_namespace

        self.terminal.step(
            f"Fetching ConfigMap '{spec['configmap_name']}' from namespace '{namespace}'..."
        )

        # Get the ConfigMap as JSON via kubectl
        _result, parsed = self.run_kubectl(
            f"configmap/{spec['configmap_name']}",
            namespace=namespace,
        )

        # kubectl gave us back nothing useful. ConfigMap is probably missing.
        if not isinstance(parsed, dict):
            raise RuntimeError(
                f"ConfigMap '{spec['configmap_name']}' not found or could not be parsed"
                f" in namespace '{namespace}'"
            )

        # Pull out the .data section
        data_section: dict[str, Any] = parsed.get("data") or {}

        if not data_section:
            raise RuntimeError(
                f"ConfigMap '{spec['configmap_name']}' in namespace '{namespace}'"
                f" has no data keys"
            )

        # Check if a specific key was requested
        requested_key: str | None = spec.get("data_key")

        if requested_key:
            if requested_key not in data_section:
                available_keys: list[str] = list(data_section.keys())
                raise RuntimeError(
                    f"Key '{requested_key}' not found in ConfigMap"
                    f" '{spec['configmap_name']}'. Available keys: {available_keys}"
                )
            content: str = data_section[requested_key]
        else:
            # No specific key requested, just grab the first one
            content = next(iter(data_section.values()))

        # Track which key we actually read so it shows up in the metadata
        actual_key: str = requested_key or next(iter(data_section.keys()))
        self._dynamic_description = (
            f"{spec['description']} - key '{actual_key}' ({len(content)} chars)"
        )

        return content
