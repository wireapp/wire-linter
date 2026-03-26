"""Checks if MinIO cluster nodes can actually talk to each other.

Queries mc admin info (tries JSON first, then falls back to text parsing) to count
how many peers are reachable. Tries the 'local' alias first, then 'myminio' if that fails.
"""

from __future__ import annotations

# External
import json
import re

# Ours
from src.lib.base_target import BaseTarget


class MinioNetworkStatus(BaseTarget):
    """Verifies MinIO cluster network connectivity across all nodes."""

    # Uses SSH to reach MinIO nodes
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """MinIO network connectivity check."""
        return "MinIO network health across all nodes"

    @property
    def explanation(self) -> str:
        """Peers need to be online for data redundancy and erasure coding to work."""
        return (
            "MinIO nodes must communicate for erasure coding and replication. "
            "Offline peers mean degraded redundancy. Healthy when all peers are online."
        )

    def collect(self) -> str:
        """Check if MinIO peers can reach each other.

        Returns:
            "X/Y OK" where X is online peers and Y is total peers checked.

        Raises:
            RuntimeError: If neither the JSON nor the text fallback can be parsed.
        """
        # Kick off the check
        self.terminal.step("Checking MinIO server info...")

        # Try JSON first way easier to parse peer status.
        # mc creds live in root's config so we need sudo.
        result = self.run_db_command(
            self.config.databases.minio,
            "sudo mc admin info local --json 2>/dev/null || sudo mc admin info myminio --json 2>/dev/null",
        )

        output: str = result.stdout.strip()

        try:
            # Deduplicate peers across all server lines so we count nodes, not directional links.
            # Each server lists N-1 peers, giving N*(N-1) entries total we collapse that to
            # N-1 unique peer hostnames so the result matches the text fallback format (e.g. 4/4).
            # Use worst-case semantics: a single "offline" sighting from any node marks the peer
            # degraded, even if other nodes report it as online (asymmetric network partition).
            seen_offline: set[str] = set()
            seen_online:  set[str] = set()

            # Each line is one JSON object, one per server in the cluster
            for line in output.split("\n"):
                line = line.strip()

                # Skip blanks
                if not line:
                    continue

                try:
                    info: dict[str, dict[str, str]] = json.loads(line)

                    # «network» field maps peer hostname to "online"/"offline"
                    network: dict[str, str] = info.get("network", {})

                    for peer, status in network.items():
                        # Accumulate into the appropriate set; never downgrade an offline sighting
                        if status == "online":
                            seen_online.add(peer)
                        else:
                            seen_offline.add(peer)

                except json.JSONDecodeError:
                    # Not JSON, skip it
                    continue

            # Merge: any peer seen offline at least once is considered offline
            all_peers: set[str] = seen_online | seen_offline
            peers: dict[str, str] = {
                peer: ("offline" if peer in seen_offline else "online")
                for peer in all_peers
            }

            # If we got any data, return the result
            if peers:
                total_count: int = len(peers)
                total_ok: int = sum(1 for s in peers.values() if s == "online")

                # Summarize network health for the report
                self._health_info = f"MinIO network: {total_ok}/{total_count} peers online"

                return f"{total_ok}/{total_count} OK"

        except (ValueError, KeyError, TypeError):
            # JSON parsing didn't work out, try text mode
            pass

        # Fall back to grepping the text output
        result2 = self.run_db_command(
            self.config.databases.minio,
            "sudo mc admin info local 2>/dev/null || sudo mc admin info myminio 2>/dev/null",
        )

        # Look for "Network: X/Y OK" pattern
        match = re.search(r"Network:\s*(\d+/\d+\s*OK)", result2.stdout)
        if match:
            # Summarize network health for the report
            self._health_info = f"MinIO network: {match.group(1)}"

            return match.group(1)

        raise RuntimeError("Could not determine MinIO network status")
