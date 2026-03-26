"""Checks SPF and DMARC DNS TXT records for the Wire deployment domain locally.

Wire sends emails (password reset, team invitations, notifications) via
the brig service. Without correct SPF and DMARC records, these emails
land in spam or are rejected entirely by recipient mail servers. See
WPB-18153.

Instead of SSH+dig on the admin host, runs dig locally on the machine
executing the script. TXT record lookups require dig since Python's
«socket» module cannot query TXT records.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget


class EmailDnsRecords(BaseTarget):
    """Verify that SPF and DMARC DNS records exist for the Wire domain.

    Uses dig locally to query TXT records on the domain (for SPF) and the
    «_dmarc» subdomain (for DMARC). Returns a summary of which records
    were found. Fails gracefully if dig is not available.
    """

    @property
    def description(self) -> str:
        """What we're checking."""
        return "SPF and DMARC email DNS records"

    @property
    def explanation(self) -> str:
        """Why it matters."""
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

        Runs «dig +short TXT <domain>» and «dig +short TXT _dmarc.<domain>»
        locally via run_local. If dig is not available, the target raises a
        RuntimeError since TXT records cannot be queried via Python stdlib.

        Returns:
            One of: «spf+dmarc», «spf_only», «dmarc_only», or «missing».

        Raises:
            RuntimeError: If dig is not available or DNS lookups fail.
        """
        domain: str = self.config.cluster.domain
        self.terminal.step(f"Checking email DNS records for {domain}...")

        # Verify dig is available before proceeding
        self._ensure_dig_available()

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

    def _ensure_dig_available(self) -> None:
        """Check that dig is installed on the local machine.

        TXT record lookups require dig since Python's socket module only
        supports A/AAAA record resolution.

        Raises:
            RuntimeError: If dig is not available.
        """
        try:
            # «which dig» exits 0 when dig is found, 1 when absent — more
            # reliable than «dig -v», which exits non-zero on some systems even
            # when dig is fully functional.
            result = self.run_local(["which", "dig"])
            if not result.success:
                raise RuntimeError(
                    "dig is not available on this machine. "
                    "TXT record lookups require dig to be installed."
                )
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(
                "dig is not available on this machine. "
                "TXT record lookups require dig to be installed."
            ) from exc

    def _check_spf(self, domain: str) -> bool:
        """Look up the SPF TXT record for the domain locally.

        Args:
            domain: The Wire deployment domain.

        Returns:
            True if an SPF record (v=spf1) exists, False otherwise.
        """
        self.terminal.step(f"Looking up SPF TXT record for {domain}...")

        result = self.run_local(["dig", "+short", "TXT", domain])
        output: str = result.stdout.strip().lower()

        # All SPF records contain v=spf1
        return "v=spf1" in output

    def _check_dmarc(self, domain: str) -> bool:
        """Look up the DMARC TXT record on _dmarc.<domain> locally.

        Args:
            domain: The Wire deployment domain.

        Returns:
            True if a DMARC record (v=DMARC1) exists, False otherwise.
        """
        dmarc_domain: str = f"_dmarc.{domain}"
        self.terminal.step(f"Looking up DMARC TXT record for {dmarc_domain}...")

        result = self.run_local(["dig", "+short", "TXT", dmarc_domain])
        output: str = result.stdout.strip().lower()

        # DMARC records contain v=dmarc1
        return "v=dmarc1" in output
