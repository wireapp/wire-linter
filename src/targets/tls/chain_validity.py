"""Checks the TLS certificate chain validity for the Wire domain.

Uses openssl s_client -showcerts to verify the full certificate chain.
Incomplete chains work in some browsers but break on mobile or strict
TLS implementations.
"""

from __future__ import annotations

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


class ChainValidity(BaseTarget):
    """Checks TLS certificate chain validity for the Wire domain.

    Connects via openssl from the admin host and inspects the verification
    result to determine if the chain is complete.
    """

    # TLS chain validity checks connect to public domain:443 requires external
    # internet access, not available from the internal admin host.
    requires_external_access: bool = True

    # Uses SSH to admin host for openssl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "TLS certificate chain validity"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "Incomplete certificate chains work in some browsers but break on mobile or "
            "strict TLS implementations. Good when openssl reports verify OK."
        )


    def collect(self) -> bool:
        """Check the TLS certificate chain via openssl s_client.

        Returns:
            True if the certificate chain is valid, False otherwise.

        Raises:
            RuntimeError: If the connection to the domain fails entirely.
        """
        domain: str = self.config.cluster.domain
        validate_domain_for_shell(domain)
        self.terminal.step(f"Checking TLS certificate chain for {domain}...")

        # openssl s_client outputs «Verify return code: 0 (ok)» on success
        cmd: str = (
            f"echo Q | openssl s_client -showcerts -connect {domain}:443"
            f" -servername {domain} 2>&1"
        )

        result = self.run_ssh(self.config.admin_host.ip, cmd)
        output: str = result.stdout

        if not output.strip():
            raise RuntimeError(f"Could not connect to {domain}:443 for TLS verification")

        # Count certificates in chain by counting BEGIN CERTIFICATE markers
        cert_count: int = output.count("BEGIN CERTIFICATE")

        # Check the verify return code 0 means the chain verified OK
        valid: bool = "Verify return code: 0 (ok)" in output

        # Extract the verify return code line for reporting
        verify_line: str = ""
        for line in output.split("\n"):
            if "Verify return code:" in line:
                verify_line = line.strip()
                break

        if valid:
            self._health_info = f"Chain valid, {cert_count} cert(s) in chain"
        else:
            self._health_info = f"Chain INVALID: {verify_line}, {cert_count} cert(s)"

        return valid
