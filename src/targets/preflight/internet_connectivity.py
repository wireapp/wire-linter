"""Tests actual internet connectivity when the deployment declares internet access.

Performs a three-step connectivity test:
1. DNS resolution of dns.google (proves DNS works for public names)
2. TCP connect to 8.8.8.8:53 (proves IP-level internet routing)
3. HTTP GET to http://www.gstatic.com/generate_204 (proves HTTP works)

If the user says they have internet but this test fails, that's a problem.
"""

from __future__ import annotations

# External
import json
import socket
import urllib.request
import urllib.error

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError


class InternetConnectivity(BaseTarget):
    """Test internet connectivity from wherever the runner executes.

    Only runs when has_internet is true in the deployment configuration.
    """

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Internet connectivity test"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "If the deployment declares internet access, we verify it actually works. "
            "Internet is needed for real AWS push notifications, AWS SES email, "
            "pulling container images, and some DNS operations."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Perform a three-step internet connectivity test.

        Returns:
            JSON string with per-step results and overall status.

        Raises:
            NotApplicableError: If internet access is not declared.
        """
        if not self.config.options.has_internet:
            raise NotApplicableError("Internet access is not declared in the deployment configuration")

        self.terminal.step("Testing internet connectivity...")

        dns_ok: bool = False
        tcp_ok: bool = False
        http_ok: bool = False
        details: list[str] = []

        # Step 1: DNS resolution of a well-known public hostname
        self.terminal.step("  DNS: resolving dns.google...")
        try:
            socket.getaddrinfo("dns.google", 53, socket.AF_INET, socket.SOCK_STREAM)
            dns_ok = True
            details.append("DNS: ok")
        except (socket.gaierror, OSError) as e:
            details.append(f"DNS: failed ({e})")

        # Step 2: TCP connect to a well-known public IP
        self.terminal.step("  TCP: connecting to 8.8.8.8:53...")
        try:
            with socket.create_connection(("8.8.8.8", 53), timeout=10):
                tcp_ok = True
                details.append("TCP: ok")
        except (socket.timeout, OSError) as e:
            details.append(f"TCP: failed ({e})")

        # Step 3: HTTP GET to a lightweight endpoint
        self.terminal.step("  HTTP: fetching http://www.gstatic.com/generate_204...")
        try:
            req = urllib.request.Request(
                "http://www.gstatic.com/generate_204",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 204:
                    http_ok = True
                    details.append("HTTP: ok (204)")
                else:
                    details.append(f"HTTP: unexpected status {resp.status}")
        except (urllib.error.URLError, OSError) as e:
            details.append(f"HTTP: failed ({e})")

        all_ok: bool = dns_ok and tcp_ok and http_ok

        result: dict[str, object] = {
            "dns_ok": dns_ok,
            "tcp_ok": tcp_ok,
            "http_ok": http_ok,
            "all_ok": all_ok,
            "details": ", ".join(details),
        }

        if all_ok:
            self._health_info = "Internet connectivity: all tests passed"
        else:
            self._health_info = f"Internet connectivity: {', '.join(details)}"

        return json.dumps(result)
