"""Checks DNS resolution of all required Wire subdomains.

Uses dig to verify each required subdomain (nginz-https, nginz-ssl, webapp,
assets, account, teams, sftd) resolves. Core subdomains should all point to
the same IP address (sftd can differ).
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


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
    """Checks DNS resolution for required Wire subdomains.

    Runs dig on the admin host to verify each subdomain resolves, then
    reports which ones succeeded and failed.
    """

    # Uses SSH to admin host for DNS lookups
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        return "DNS resolution of required Wire subdomains"

    @property
    def explanation(self) -> str:
        return (
            "Clients reach Wire services through specific subdomains like «nginz-https», "
            "«webapp», «assets». If DNS doesn't resolve these, the services are unreachable. "
            "Everything's good when all subdomains resolve."
        )

    def collect(self) -> str:
        """Resolve all required Wire subdomains via dig on the admin host.

        Returns:
            Comma-separated list of resolved subdomains.

        Raises:
            RuntimeError: If no subdomains resolve.
        """
        domain: str = self.config.cluster.domain

        resolved: list[str] = []
        failed: list[str] = []
        ip_map: dict[str, str] = {}

        for subdomain in _REQUIRED_SUBDOMAINS:
            fqdn: str = f"{subdomain}.{domain}"
            validate_domain_for_shell(fqdn)
            self.terminal.step(f"Resolving {fqdn}...")

            # dig +short gives us just the IP addresses, no extra formatting
            result = self.run_ssh(
                self.config.admin_host.ip,
                f"dig +short {fqdn}",
            )

            # Empty output means the name didn't resolve
            answer: str = result.stdout.strip()

            if answer:
                resolved.append(subdomain)
                # Track the first IP returned (used to check consistency across subdomains)
                first_ip: str = answer.split("\n")[0]
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
