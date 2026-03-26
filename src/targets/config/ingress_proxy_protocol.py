"""Checks the ingress-nginx proxy protocol configuration.

When a load balancer sends PROXY protocol headers but ingress-nginx isn't
configured to accept them (or vice versa), HTTP requests fail with 400
errors or garbage responses. Spotting this misconfiguration prevents
silent connectivity failures. See WPB-17802.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Namespaces where ingress-nginx is commonly deployed. Includes default
# because WIAB (Wire-in-a-Box) puts it there
_INGRESS_NAMESPACES: list[str] = [
    "ingress-nginx",
    "default",
    "kube-system",
]

# ConfigMap names used by ingress-nginx for its configuration
_INGRESS_CONFIGMAP_NAMES: list[str] = [
    "ingress-nginx-controller",
    "nginx-ingress-controller",
    "nginx-configuration",
    "ingress-nginx",
]


class IngressProxyProtocol(BaseTarget):
    """Checks the ingress-nginx proxy protocol configuration.

    Fetches the ingress-nginx controller ConfigMap and looks at the
    use-proxy-protocol key. Returns a string describing the current proxy
    protocol state, so operators can verify it matches their load balancer
    config.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "ingress-nginx proxy protocol configuration"

    @property
    def explanation(self) -> str:
        """Why we're checking and what's healthy vs unhealthy."""
        return (
            "If the load balancer sends PROXY protocol headers but ingress-nginx "
            "isn't configured to accept them (or vice versa), all HTTP requests fail "
            "silently. This check shows the current nginx proxy protocol setting so "
            "operators can verify it matches the LB config (WPB-17802)."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement (empty, result is a string)."""
        return ""

    def collect(self) -> str:
        """Read the proxy protocol setting from the ingress-nginx ConfigMap.

        Returns:
            String describing the proxy protocol state:
            "enabled", "disabled", or "not_found" if the ConfigMap was
            not found in any known namespace.

        Raises:
            RuntimeError: If kubectl fails for all namespace/name combinations.
        """
        self.terminal.step("Checking ingress-nginx proxy protocol config...")

        cm_data: dict[str, Any] | None = self._find_ingress_configmap()

        if cm_data is None:
            self._health_info = (
                "ingress-nginx ConfigMap not found in known namespaces. "
                "Check manually if PROXY protocol is correctly configured."
            )
            return "not_found"

        # ConfigMap data section holds nginx config keys as strings
        config_data: dict[str, str] = cm_data.get("data", {})

        # Key that controls proxy protocol ingestion in ingress-nginx
        proxy_protocol_value: str = str(
            config_data.get("use-proxy-protocol", "")
        ).strip().lower()

        # Related settings that affect proxy protocol behavior
        real_ip_cidr: str = config_data.get("proxy-real-ip-cidr", "")
        set_real_ip_from: str = config_data.get("set-real-ip-from", "")

        use_proxy_protocol: bool = proxy_protocol_value in ("true", "1", "yes", "on")

        if use_proxy_protocol:
            self._health_info = (
                "use-proxy-protocol=true (ingress-nginx expects PROXY protocol from LB). "
                "Ensure the load balancer is sending PROXY protocol headers."
            )
            return "enabled"
        else:
            setting_display: str = proxy_protocol_value if proxy_protocol_value else "(not set)"
            self._health_info = (
                f"use-proxy-protocol={setting_display} "
                "(ingress-nginx does NOT expect PROXY protocol). "
                "Ensure the load balancer is NOT sending PROXY protocol headers."
            )
            return "disabled"

    def _find_ingress_configmap(self) -> dict[str, Any] | None:
        """Find the ingress-nginx ConfigMap by trying known namespaces and names.

        Returns:
            Parsed ConfigMap dict, or None if we can't find it.
        """
        for namespace in _INGRESS_NAMESPACES:
            for cm_name in _INGRESS_CONFIGMAP_NAMES:
                try:
                    _result, data = self.run_kubectl(
                        f"configmap/{cm_name}",
                        namespace=namespace,
                    )
                    if isinstance(data, dict) and data.get("kind") == "ConfigMap":
                        self.terminal.step(
                            f"Found ingress-nginx ConfigMap: "
                            f"{cm_name} in {namespace}"
                        )
                        return data
                except Exception:
                    continue

        return None
