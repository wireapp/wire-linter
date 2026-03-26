"""Checks TLS configuration on Ingress resources.

Ingresses without TLS configuration serve traffic over plain HTTP.
In production, every ingress host should be covered by a TLS entry
to ensure encrypted connections.

Produces a single data point at « kubernetes/ingress/tls_config ».
Value is a JSON string with TLS coverage details per ingress.
"""

from __future__ import annotations

import fnmatch
import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class IngressTlsConfig(BaseTarget):
    """Checks TLS configuration on all Ingress resources.

    Fetches all ingresses and compares which hosts are defined in
    spec.rules against which hosts are covered by spec.tls entries.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Ingress TLS configuration"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Ingresses without TLS configuration serve traffic over plain HTTP. "
            "Every production ingress host should be covered by a TLS entry."
        )

    def collect(self) -> str:
        """Fetch ingresses and check TLS coverage.

        Returns:
            JSON string with TLS coverage details.
        """
        self.terminal.step("Checking ingress TLS configuration...")

        _result, parsed = self.run_kubectl(
            "ingress", all_namespaces=True
        )

        details: list[dict[str, Any]] = []
        total_ingresses: int = 0
        with_tls: int = 0
        without_tls: int = 0

        if isinstance(parsed, dict):
            for item in parsed.get("items", []):
                total_ingresses += 1

                ingress_name: str = item.get("metadata", {}).get("name", "")
                ingress_ns: str = item.get("metadata", {}).get("namespace", "")
                spec: dict[str, Any] = item.get("spec", {})

                # Collect all hosts from rules
                rule_hosts: list[str] = []
                for rule in spec.get("rules", []):
                    host: str | None = rule.get("host")
                    if host:
                        rule_hosts.append(host)

                # Collect all hosts covered by TLS
                tls_hosts: list[str] = []
                for tls_entry in spec.get("tls", []):
                    for host in tls_entry.get("hosts", []):
                        tls_hosts.append(host)

                # Find hosts not covered by TLS (wildcard-aware, e.g. *.example.com covers foo.example.com)
                uncovered_hosts: list[str] = [
                    h for h in rule_hosts
                    if not any(fnmatch.fnmatch(h, tls_h) for tls_h in tls_hosts)
                ]

                has_tls: bool = len(spec.get("tls", [])) > 0
                if has_tls:
                    with_tls += 1
                else:
                    without_tls += 1

                details.append({
                    "name": ingress_name,
                    "namespace": ingress_ns,
                    "hosts": rule_hosts,
                    "tls_hosts": tls_hosts,
                    "uncovered_hosts": uncovered_hosts,
                    "has_tls": has_tls,
                })

        if without_tls > 0:
            self._health_info = f"{without_tls}/{total_ingresses} ingress(es) without TLS"
        else:
            self._health_info = f"All {total_ingresses} ingress(es) have TLS"

        return json.dumps({
            "total_ingresses": total_ingresses,
            "with_tls": with_tls,
            "without_tls": without_tls,
            "details": details,
        }, sort_keys=True)
