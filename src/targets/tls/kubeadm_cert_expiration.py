"""Checks Kubernetes internal certificate expiration via kubeadm.

Runs kubeadm certs check-expiration on a control plane node via SSH.
These certs expire after 1 year by default if missed, the entire
Kubernetes control plane dies.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class KubeadmCertExpiration(BaseTarget):
    """Checks kubeadm certificate expiration on a control plane node.

    SSHes to the first kubenode and runs kubeadm certs check-expiration
    to report the earliest expiring internal certificate.
    """

    # Uses SSH to reach control plane nodes for cert checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Kubernetes internal certificate expiration (kubeadm)"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Kubeadm certs expire after 1 year by default. If missed, the entire "
            "Kubernetes control plane dies. Below 30 days is critical."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement empty because result is a status string."""
        return ""

    def collect(self) -> str:
        """Run kubeadm certs check-expiration on a control plane node.

        Returns:
            Summary string with the earliest expiring certificate info.

        Raises:
            RuntimeError: If kubeadm is not available or no kubenodes found.
        """
        self.terminal.step("Checking kubeadm certificate expiration...")

        # Get the first kubenode IP to SSH into
        _cmd_result, data = self.run_kubectl("nodes")
        if data is None:
            raise RuntimeError("Failed to get nodes from kubectl")

        items: list[dict[str, Any]] = data.get("items", [])
        if not items:
            raise RuntimeError("No nodes found in cluster")

        # Find the first node's InternalIP
        first_ip: str | None = None
        for addr in items[0].get("status", {}).get("addresses", []):
            if addr.get("type") == "InternalIP":
                first_ip = addr.get("address")
                break

        if not first_ip:
            raise RuntimeError("Could not determine IP of first kubenode")

        # kubeadm certs check-expiration requires root privileges
        result = self.run_ssh(
            first_ip,
            "sudo kubeadm certs check-expiration 2>/dev/null"
            " || sudo /usr/local/bin/kubeadm certs check-expiration 2>/dev/null",
        )

        output: str = result.stdout.strip()

        if not output:
            raise RuntimeError("kubeadm certs check-expiration returned no output")

        # Parse the table output to find the earliest expiring cert
        # Lines look like: «admin.conf    Mar 15, 2026 12:00 UTC   364d   ca»
        # Near-expiry certs may show hours/minutes: «11h», «30m»
        earliest_days: float | None = None
        earliest_name: str = ""
        cert_count: int = 0

        for line in output.split("\n"):
            # Skip header and separator lines
            stripped: str = line.strip()
            if not stripped or stripped.startswith("CERTIFICATE") or stripped.startswith("!"):
                continue

            # Look for lines with time remaining like «364d», «11h», «30m»
            parts: list[str] = stripped.split()

            # Only count lines that are actual certificate rows, not headers, info lines,
            # or future summary lines that might incidentally contain duration tokens.
            # A valid cert row either uses pipe-delimited format (| cert_name | ...) or
            # starts with a lowercase cert name (e.g., admin.conf, apiserver, etcd-ca).
            # This rejects [check-expiration] info lines, +---+ separators, and capitalized words.
            first_part: str = parts[0].strip("|").strip() if parts else ""
            is_cert_row: bool = (
                "|" in stripped
                or (
                    bool(first_part)
                    and first_part[0].islower()
                    and all(c.isalnum() or c in "._/-" for c in first_part)
                )
            )
            if not is_cert_row:
                continue

            for part in parts:
                # Convert all time units to fractional days so thresholds work uniformly
                days: float | None = None
                if part.endswith("d") and part[:-1].isdigit():
                    # Full days most common case
                    days = float(part[:-1])
                elif part.endswith("h") and part[:-1].isdigit():
                    # Hours → fractional days (cert expiring very soon)
                    days = int(part[:-1]) / 24.0
                elif part.endswith("m") and part[:-1].isdigit():
                    # Minutes → fractional days (cert expiring imminently)
                    days = int(part[:-1]) / 1440.0

                if days is not None:
                    cert_count += 1
                    if earliest_days is None or days < earliest_days:
                        earliest_days = days
                        # Use first_part (pipe-stripped) so name is clean in output
                        earliest_name = first_part
                    break

        if earliest_days is not None:
            # Format as integer days when whole, fractional otherwise for readability
            days_str: str = f"{int(earliest_days)}d" if earliest_days >= 1 and earliest_days == int(earliest_days) else f"{earliest_days:.2f}d"
            if earliest_days <= 30:
                self._health_info = f"CRITICAL: '{earliest_name}' expires in {days_str}, {cert_count} certs checked"
            elif earliest_days <= 90:
                self._health_info = f"WARNING: '{earliest_name}' expires in {days_str}, {cert_count} certs checked"
            else:
                self._health_info = f"Earliest expiry: '{earliest_name}' in {days_str}, {cert_count} certs checked"

            return f"{days_str} ({earliest_name})"

        # Could not parse days return raw output summary
        self._health_info = "Could not parse certificate expiry days from kubeadm output"
        # Return first meaningful line as value
        for line in output.split("\n"):
            if line.strip() and not line.strip().startswith("CERTIFICATE"):
                return line.strip()[:100]

        return output[:100]
