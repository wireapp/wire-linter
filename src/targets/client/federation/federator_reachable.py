"""Tests if the federator endpoint is reachable from a client network.

Part of --source client mode. The federator uses mutual TLS, so we may not
complete the handshake without a client cert, but we can verify the port
is open and TLS is offered.
"""

from __future__ import annotations

# External
import json
import socket
import ssl

# Ours
from src.lib.base_target import BaseTarget, NotApplicableError, SourceMode


class ClientFederatorReachable(BaseTarget):
    """Test if the federator endpoint is reachable via TLS.

    Only runs in client mode when federation is enabled.
    """

    # Only runs in client mode
    source_mode: SourceMode = SourceMode.CLIENT

    @property
    def description(self) -> str:
        """What this target checks."""
        return "Federator endpoint reachability from client network"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "The federator handles incoming connections from federated backends. "
            "While clients don't directly contact it, verifying reachability from "
            "the client network is useful diagnostic information."
        )

    @property
    def unit(self) -> str:
        """No unit — returns structured JSON string."""
        return ""

    def collect(self) -> str:
        """Test TLS connectivity to the federator endpoint.

        Returns:
            JSON string with reachability details.

        Raises:
            NotApplicableError: If federation is not enabled.
        """
        if not self.config.options.expect_federation:
            raise NotApplicableError("Federation is not enabled")

        domain: str = self.config.cluster.domain
        hostname: str = f"federator.{domain}"

        self.terminal.step(f"Testing federator reachability: {hostname}:443")

        reachable: bool = False
        tls_offered: bool = False
        error_msg: str = ""

        try:
            # Try a basic TCP + TLS connection
            # The federator uses mutual TLS, so we may get a handshake error
            # (no client cert) — but that still proves the port is open
            raw_sock = socket.create_connection((hostname, 443), timeout=10)

            # Try TLS — accept any cert since we're just testing connectivity
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            try:
                tls_sock = ctx.wrap_socket(raw_sock, server_hostname=hostname)
                tls_offered = True
                reachable = True
                tls_sock.close()
            except ssl.SSLError:
                # TLS error means port is open but TLS failed — still reachable
                tls_offered = True
                reachable = True
                raw_sock.close()

        except socket.gaierror as e:
            error_msg = f"DNS resolution failed: {e}"
        except (socket.timeout, OSError) as e:
            error_msg = f"Connection failed: {e}"

        result: dict[str, object] = {
            "hostname": hostname,
            "reachable": reachable,
            "tls_offered": tls_offered,
            "error": error_msg,
        }

        if reachable:
            self._health_info = f"Federator reachable at {hostname}:443 (TLS: {'yes' if tls_offered else 'no'})"
        else:
            self._health_info = f"Federator NOT reachable at {hostname}:443 — {error_msg}"

        return json.dumps(result)
