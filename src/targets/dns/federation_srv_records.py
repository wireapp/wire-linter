"""Resolves DNS SRV records for federation partner domains.

Federation discovery uses DNS SRV records of the form:
_wire-server-federator._tcp.<domain>
to find the infrastructure domain where the federator is reachable.
"""

from __future__ import annotations

# External
import json
import socket
import subprocess
from typing import Any

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class FederationSrvRecords(BaseTarget):
    """Resolve DNS SRV records for each declared federation partner domain.

    Only runs when federation is enabled and federation_domains is non-empty.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federation DNS SRV records for partner domains"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Federation uses DNS SRV records (_wire-server-federator._tcp.<domain>) "
            "to discover where each partner's federator is reachable. Without valid "
            "SRV records, the federator cannot discover remote backends."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Resolve SRV records for each federation partner domain.

        Returns:
            JSON string with per-domain SRV resolution results.

        Raises:
            NotApplicableError: If federation is not enabled or no domains declared.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")

        domains: list[str] = self.config.options.federation_domains or []
        if not domains:
            raise NotApplicableError("No federation partner domains declared")

        if not self.config.options.has_dns:
            raise NotApplicableError("DNS is not available in this deployment")

        self.terminal.step("Resolving federation SRV records for partner domains...")

        results: list[dict[str, Any]] = []

        for domain in domains:
            srv_name: str = f"_wire-server-federator._tcp.{domain}"
            self.terminal.step(f"  Resolving {srv_name}...")

            srv_found: bool = False
            target: str = ""
            port: int = 0
            ttl: int = 0
            error_msg: str = ""

            try:
                # Use the dig command for SRV lookups (stdlib doesn't support SRV directly)
                result = subprocess.run(
                    ["dig", "+short", "SRV", srv_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                output: str = result.stdout.strip()
                if output and not output.startswith(";"):
                    # SRV format: priority weight port target
                    parts: list[str] = output.split()
                    if len(parts) >= 4:
                        port = int(parts[2])
                        target = parts[3].rstrip(".")
                        srv_found = True
                elif result.returncode != 0:
                    error_msg = result.stderr.strip() or "dig command failed"
                else:
                    error_msg = "No SRV record found"

            except FileNotFoundError:
                # dig not available, fall back to nslookup
                try:
                    result = subprocess.run(
                        ["nslookup", "-type=SRV", srv_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    output = result.stdout
                    # Parse nslookup SRV output (less reliable)
                    if "service" in output.lower() or "port" in output.lower():
                        srv_found = True
                        target = "see raw output"
                    else:
                        error_msg = "No SRV record found (via nslookup)"
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    error_msg = "Neither dig nor nslookup available"

            except subprocess.TimeoutExpired:
                error_msg = "DNS lookup timed out"

            results.append({
                "domain": domain,
                "srv_name": srv_name,
                "srv_found": srv_found,
                "target": target,
                "port": port,
                "ttl": ttl,
                "error": error_msg,
            })

        resolved_count: int = sum(1 for r in results if r["srv_found"])
        total_count: int = len(results)

        output_data: dict[str, Any] = {
            "results": results,
            "resolved_count": resolved_count,
            "total_count": total_count,
        }

        if resolved_count == total_count:
            self._health_info = f"All {total_count} federation SRV records resolved"
        else:
            failed: list[str] = [r["domain"] for r in results if not r["srv_found"]]
            self._health_info = f"{resolved_count}/{total_count} resolved. Missing: {', '.join(failed)}"

        return json.dumps(output_data)
