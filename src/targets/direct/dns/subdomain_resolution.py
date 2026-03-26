"""Checks DNS resolution of all required Wire subdomains locally.

Instead of SSH+dig on the admin host, runs dig locally on the machine executing
the script. Falls back to Python's «socket.getaddrinfo()» for A record resolution
if dig is not available.

Uses the same subdomain list as the SSH version: nginz-https, nginz-ssl, webapp,
assets, account, teams, sftd.
"""

from __future__ import annotations

# External
import shutil
import socket
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


# Every Wire deployment needs DNS records for these subdomains
_REQUIRED_SUBDOMAINS: list[str] = [
    "nginz-https",
    "nginz-ssl",
    "webapp",
    "assets",
    "account",
    "teams",
    "sftd",
]


class SubdomainResolution(BaseTarget):
    """Checks DNS resolution for required Wire subdomains locally.

    Runs dig on the local machine to verify each subdomain resolves. If dig is
    not installed, falls back to Python's socket module for A record resolution.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "DNS resolution of required Wire subdomains"

    @property
    def explanation(self) -> str:
        """Why it matters."""
        return (
            "Clients reach Wire services through specific subdomains like «nginz-https», "
            "«webapp», «assets». If DNS doesn't resolve these, the services are unreachable. "
            "Everything's good when all subdomains resolve."
        )

    def collect(self) -> str:
        """Resolve all required Wire subdomains via local dig or socket fallback.

        Tries dig first (via run_local). If dig is unavailable (command fails),
        falls back to «socket.getaddrinfo()» for A record lookups.

        Returns:
            Comma-separated list of resolved subdomains.

        Raises:
            RuntimeError: If no subdomains resolve.
        """
        domain: str = self.config.cluster.domain

        resolved: list[str] = []
        failed: list[str] = []
        ip_map: dict[str, str] = {}

        # Try dig first to determine if it's available
        has_dig: bool = self._check_dig_available()

        for subdomain in _REQUIRED_SUBDOMAINS:
            fqdn: str = f"{subdomain}.{domain}"
            self.terminal.step(f"Resolving {fqdn}...")

            if has_dig:
                answer: str = self._resolve_with_dig(fqdn)
            else:
                answer = self._resolve_with_socket(fqdn)

            if answer:
                resolved.append(subdomain)
                # Track the first IP returned (used to check consistency across subdomains)
                first_ip: str = answer.split("\n")[0].strip()
                ip_map[subdomain] = first_ip
            else:
                failed.append(subdomain)

        # Separate core subdomains (everything except sftd)
        core_subdomains: list[str] = [s for s in resolved if s != "sftd"]
        core_ips: set[str] = {ip_map[s] for s in core_subdomains if s in ip_map}

        # Report what we found
        if failed:
            self._health_info = (
                f"{len(resolved)}/{len(_REQUIRED_SUBDOMAINS)} resolved, "
                f"missing: {', '.join(failed)}"
            )
        elif len(core_ips) > 1:
            self._health_info = (
                f"All resolved, but core subdomains point to different IPs: "
                f"{', '.join(f'{s}={ip_map[s]}' for s in core_subdomains)}"
            )
        else:
            self._health_info = f"All {len(resolved)} subdomains resolved"

        if not resolved:
            raise RuntimeError(f"No required subdomains resolved for domain {domain}")

        return ", ".join(resolved)

    def _check_dig_available(self) -> bool:
        """Check if dig is installed on the local machine.

        Uses shutil.which() to check if the dig binary is on PATH, avoiding
        reliance on exit codes which vary across distributions (dig -v exits
        non-zero on many Linux systems).

        Returns:
            True if dig is available, False otherwise.
        """
        return shutil.which("dig") is not None

    def _resolve_with_dig(self, fqdn: str) -> str:
        """Resolve a domain using dig locally.

        Args:
            fqdn: The fully qualified domain name to resolve.

        Returns:
            The dig output (IP addresses), or empty string if resolution fails.
        """
        result = self.run_local(["dig", "+short", fqdn])
        return result.stdout.strip()

    def _resolve_with_socket(self, fqdn: str) -> str:
        """Resolve a domain using Python's socket module as fallback.

        Uses «socket.getaddrinfo()» for A record resolution. Only returns
        IPv4 addresses (AF_INET).

        Args:
            fqdn: The fully qualified domain name to resolve.

        Returns:
            The first resolved IP address, or empty string if resolution fails.
        """
        try:
            # Get A records (IPv4) for the domain
            results: list[tuple[Any, ...]] = socket.getaddrinfo(
                fqdn, None, socket.AF_INET, socket.SOCK_STREAM,
            )

            if results:
                # getaddrinfo returns (family, type, proto, canonname, sockaddr)
                # sockaddr is (address, port) for IPv4
                ip_address: str = results[0][4][0]
                return ip_address

        except socket.gaierror:
            # Name resolution failed
            pass

        return ""
