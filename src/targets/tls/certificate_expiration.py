"""Checks the TLS certificate expiration date for the Wire domain.

Uses openssl s_client to connect to the domain on port 443 and extract the
certificate's notAfter date. Reports the number of days until expiry.
"""

from __future__ import annotations

# External
import datetime
import re

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


class CertificateExpiration(BaseTarget):
    """Checks TLS certificate expiration for the Wire domain.

    Connects to the domain via openssl from the admin host and parses the
    notAfter date to calculate days remaining until expiry.
    """

    # TLS certificate checks connect to public domain:443 this needs an
    # externally routable machine, not the internal admin host.
    requires_external_access: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "TLS certificate days until expiration"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "An expired TLS certificate makes the whole deployment unreachable for "
            "all clients. Below 14 days is critical, below 30 is a warning."
        )

    @property
    def unit(self) -> str:
        """Unit of measurement for the returned value."""
        return "days"

    def collect(self) -> int:
        """Check the TLS certificate expiration date via openssl.

        Returns:
            Number of days until the certificate expires.

        Raises:
            RuntimeError: If the certificate cannot be retrieved or parsed.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        self.terminal.step(f"Checking TLS certificate expiration for {domain}...")

        # requires_external_access=True means the gatherer machine has internet access
        # so run openssl locally rather than via the admin host which is on a
        # private network and can't reach public domain:443
        cmd: str = (
            f"openssl s_client -connect {domain}:443 -servername {domain} "
            f"< /dev/null 2>/dev/null"
            f" | openssl x509 -noout -enddate 2>/dev/null"
        )

        result = self.run_local(["sh", "-c", cmd])
        output: str = result.stdout.strip()

        # Output format: notAfter=Mar 15 12:00:00 2025 GMT
        if not output.startswith("notAfter="):
            raise RuntimeError(f"Could not retrieve TLS certificate for {domain}")

        expiry_str: str = output.split("=", 1)[1].strip()

        # Strip the trailing timezone abbreviation (e.g. «GMT» or «UTC») before
        # parsing because %Z behavior is platform-dependent: Python 3.10 on some
        # systems raises ValueError for «GMT», while 3.11+ may produce aware or
        # naive datetimes. Some openssl builds (Alpine/musl, certain BSDs) output
        # «UTC» instead of «GMT». We strip any 2-4 letter uppercase tz suffix.
        date_str: str = re.sub(r'\s+[A-Z]{2,4}$', '', expiry_str).strip()

        # openssl notAfter format (without tz): «Mar 15 12:00:00 2025»
        try:
            expiry_dt: datetime.datetime = datetime.datetime.strptime(date_str, "%b %d %H:%M:%S %Y")
        except ValueError:
            raise RuntimeError(f"Could not parse certificate expiry date: {expiry_str!r}")

        # openssl notAfter is always UTC, attach timezone for well-defined arithmetic
        expiry_dt = expiry_dt.replace(tzinfo=datetime.timezone.utc)

        # Compute days remaining locally no second SSH call needed
        days_remaining: int = (expiry_dt - datetime.datetime.now(datetime.timezone.utc)).days

        # Report health based on days remaining
        if days_remaining <= 0:
            self._health_info = f"EXPIRED ({expiry_str})"
        elif days_remaining <= 14:
            self._health_info = f"CRITICAL: expires in {days_remaining} days ({expiry_str})"
        elif days_remaining <= 30:
            self._health_info = f"WARNING: expires in {days_remaining} days ({expiry_str})"
        else:
            self._health_info = f"Expires in {days_remaining} days ({expiry_str})"

        return days_remaining
