"""Checks SPF and DMARC DNS TXT records for the Wire deployment domain.

Wire sends emails (password reset, team invitations, notifications) via
the brig service. Without correct SPF and DMARC records, these emails
land in spam or are rejected entirely by recipient mail servers. See
WPB-18153.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


class EmailDnsRecords(BaseTarget):
    """Verify that SPF and DMARC DNS records exist for the Wire domain.

    Uses dig to query TXT records on the domain (for «SPF») and the
    _dmarc subdomain (for «DMARC») from the admin host. Returns a summary
    of which records were found.
    """

    # Uses SSH to admin host for DNS lookups
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """SPF and DMARC DNS records."""
        return "SPF and DMARC email DNS records"

    @property
    def explanation(self) -> str:
        """Wire emails like password reset and team invitations get rejected or
        spam-folded without proper «SPF» and «DMARC» DNS records. The check passes
        when both «v=spf1» and «v=DMARC1» TXT records are present (WPB-18153)."""
        return (
            "Wire emails (password reset, invitations) are rejected or spam-folded "
            "without SPF and DMARC DNS records. Both v=spf1 and v=DMARC1 records "
            "must be present (WPB-18153)."
        )

    @property
    def unit(self) -> str:
        """No unit. Result is a string, not a number."""
        return ""

    def collect(self) -> str:
        """Verify both SPF and DMARC records exist for the Wire domain.

        Returns:
            One of: "spf+dmarc", "spf_only", "dmarc_only", or "missing".

        Raises:
            RuntimeError: If DNS lookups fail.
        """
        domain: str = self.config.cluster.domain
        self.terminal.step(f"Checking email DNS records for {domain}...")

        has_spf: bool = self._check_spf(domain)
        has_dmarc: bool = self._check_dmarc(domain)

        found: list[str] = []
        missing: list[str] = []

        if has_spf:
            found.append("SPF")
        else:
            missing.append("SPF")

        if has_dmarc:
            found.append("DMARC")
        else:
            missing.append("DMARC")

        if found and not missing:
            self._health_info = (
                f"Both SPF and DMARC records present for {domain}"
            )
            return "spf+dmarc"

        if missing:
            self._health_info = (
                f"Missing email DNS record(s) for {domain}: "
                f"{', '.join(missing)}. Outgoing Wire emails may be rejected as spam."
            )

        if has_spf and not has_dmarc:
            return "spf_only"

        if has_dmarc and not has_spf:
            return "dmarc_only"

        return "missing"

    def _check_spf(self, domain: str) -> bool:
        """Look up the SPF TXT record for the domain.

        Args:
            domain: The Wire deployment domain.

        Returns:
            True if an «SPF» record (v=spf1) exists, False otherwise.
        """
        validate_domain_for_shell(domain)
        self.terminal.step(f"Looking up SPF TXT record for {domain}...")

        result = self.run_ssh(
            self.config.admin_host.ip,
            f"dig +short TXT {domain} 2>/dev/null",
        )

        output: str = result.stdout.strip().lower()

        # All SPF records contain v=spf1
        return "v=spf1" in output

    def _check_dmarc(self, domain: str) -> bool:
        """Look up the DMARC TXT record on _dmarc.<domain>.

        Args:
            domain: The Wire deployment domain.

        Returns:
            True if a «DMARC» record (v=DMARC1) exists, False otherwise.
        """
        validate_domain_for_shell(domain)
        dmarc_domain: str = f"_dmarc.{domain}"
        self.terminal.step(f"Looking up DMARC TXT record for {dmarc_domain}...")

        result = self.run_ssh(
            self.config.admin_host.ip,
            f"dig +short TXT {dmarc_domain} 2>/dev/null",
        )

        output: str = result.stdout.strip().lower()

        # DMARC records contain v=dmarc1
        return "v=dmarc1" in output
