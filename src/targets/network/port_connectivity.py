"""Tests TCP port connectivity between cluster nodes.

Checks that kubenodes can reach datanodes on database ports, that kubenodes
can reach each other on kubernetes control plane ports, and that datanodes
reach each other on replication/gossip ports. We batch all port tests for a
single source host into one SSH command (more efficient).

Port matrix:
    kubenode -> datanode:  9042, 7000, 9200, 9300, 5432, 9000, 5672, 15672
    kubenode -> kubenode:  6443, 2379, 2380, 10250
    datanode -> datanode:  7000, 9300, 9000

Related modules:
    src/lib/vm_hosts.py     -- shared host discovery
    src/lib/per_host_target.py -- base class for per-host iteration
"""

from __future__ import annotations

import ipaddress
from typing import Any

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


# Ports a kubenode must be able to reach on every datanode
_KUBE_TO_DATA_PORTS: list[dict[str, str | int]] = [
    {"port": 9042,  "service": "Cassandra CQL"},
    {"port": 7000,  "service": "Cassandra gossip"},
    {"port": 9200,  "service": "OpenSearch REST"},
    {"port": 9300,  "service": "OpenSearch transport"},
    {"port": 5432,  "service": "PostgreSQL"},
    {"port": 9000,  "service": "MinIO S3"},
    {"port": 5672,  "service": "RabbitMQ AMQP"},
    {"port": 15672, "service": "RabbitMQ mgmt"},
]

# Ports a kubenode must be able to reach on every other kubenode
_KUBE_TO_KUBE_PORTS: list[dict[str, str | int]] = [
    {"port": 6443,  "service": "kube-apiserver"},
    {"port": 2379,  "service": "etcd client"},
    {"port": 2380,  "service": "etcd peer"},
    {"port": 10250, "service": "kubelet"},
]

# Ports a datanode must be able to reach on every other datanode
_DATA_TO_DATA_PORTS: list[dict[str, str | int]] = [
    {"port": 7000, "service": "Cassandra gossip"},
    {"port": 9300, "service": "OpenSearch transport"},
    {"port": 9000, "service": "MinIO replication"},
]


def _validate_ip_address(ip: str) -> None:
    """Validate that ip is a valid IPv4 or IPv6 address.

    Uses ipaddress module from stdlib, which will reject anything with shell
    metacharacters (spaces, quotes, etc.) since those aren't valid in an IP.
    This blocks command injection if we end up in a shell command.

    Args:
        ip: String to validate.

    Raises:
        ValueError: If ip is not a valid IPv4 or IPv6 address literal.
    """
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(
            f"Refusing to build shell command: {ip!r} is not a valid IP address"
        )


def _build_port_test_command(target_ip: str, port: int) -> str:
    """Build a shell command to test one TCP port with fallback.

    Tries bash /dev/tcp first (works on most Linux without extra packages),
    then falls back to netcat if /dev/tcp isn't available.

    Args:
        target_ip: IP address of the target host.
        port:      TCP port number to test.

    Returns:
        A shell command string that prints exit code (0 = open).
    """
    # Validate before putting in shell (prevents injection if kubectl returns something weird)
    _validate_ip_address(target_ip)

    # Try /dev/tcp first (it's a bash builtin, fast), then nc -z as fallback
    return (
        f'{{ timeout 3 bash -c "echo >/dev/tcp/{target_ip}/{port}" 2>/dev/null'
        f' && echo "PORT {target_ip} {port} OPEN"; }}'
        f' || {{ nc -z -w 3 {target_ip} {port} 2>/dev/null'
        f' && echo "PORT {target_ip} {port} OPEN"'
        f' || echo "PORT {target_ip} {port} CLOSED"; }}'
    )


class PortConnectivity(PerHostTarget):
    """Tests TCP connectivity between hosts in the cluster.

    SSH into each host and test all the ports it needs to reach. Batches
    everything for one host into a single SSH command.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target checks."""
        return "Inter-node TCP port connectivity"

    @property
    def explanation(self) -> str:
        """Why this check exists and what determines healthy vs unhealthy."""
        return (
            "If cluster nodes can't reach each other on service ports, stuff silently breaks. "
            "Cassandra down means messages don't flow, etcd issues mean kubernetes goes wonky. "
            "We test all the ports between kubenodes and datanodes."
        )

    @property
    def unit(self) -> str:
        """Unit label shown next to the collected value."""
        return "ports"

    def get_hosts(self) -> list[dict[str, str]]:
        """Return all cluster hosts (kubenodes + datanodes).

        Reuses the shared vm_hosts discovery module so the host list stays
        consistent with other per-host targets like disk_usage. The result
        is cached in instance state so collect_for_host() can reuse it
        without triggering a second kubectl invocation per host.

        Returns:
            List of host dicts with 'name' and 'ip' keys.
        """
        # Cache once collect_for_host() reads self._all_vm_hosts directly
        self._all_vm_hosts: list[dict[str, str]] = discover_vm_hosts(self.config, self.run_kubectl)
        return self._all_vm_hosts

    def collect_for_host(self, host: dict[str, str]) -> str:
        """Test TCP port connectivity from this host to all relevant targets.

        Determines which ports to test based on the source host type (kubenode
        vs datanode) and the target host type, then batches all tests into a
        single SSH command for efficiency.

        Args:
            host: Dict with 'name' and 'ip' keys for the source host.

        Returns:
            Summary string like "15/18 open".
        """
        source_name: str = host["name"]
        source_ip: str = host["ip"]

        # Determine whether this source is a kubenode or datanode based on name prefix.
        # Both types now use IP-based names: kubenode-{ip} or datanode-{ip}.
        is_kubenode: bool = source_name.startswith("kubenode-")

        # Reuse the host list cached by get_hosts() if available; otherwise
        # discover it now so collect_for_host() works when called directly
        # (e.g. in unit tests) without a prior get_hosts() call.
        if not hasattr(self, "_all_vm_hosts"):
            self._all_vm_hosts = discover_vm_hosts(self.config, self.run_kubectl)
        all_hosts: list[dict[str, str]] = self._all_vm_hosts

        # Separate kubenodes from datanodes for the port matrix
        kubenodes: list[dict[str, str]] = [
            h for h in all_hosts if h["name"].startswith("kubenode-")
        ]
        datanodes: list[dict[str, str]] = [
            h for h in all_hosts if h["name"].startswith("datanode-")
        ]

        # Build the list of (target_host, port_info) pairs to test
        test_pairs: list[tuple[dict[str, str], dict[str, str | int]]] = []

        if is_kubenode:
            # Kubenode -> every datanode on database service ports
            for target in datanodes:
                for port_info in _KUBE_TO_DATA_PORTS:
                    test_pairs.append((target, port_info))

            # Kubenode -> every other kubenode on Kubernetes control plane ports
            for target in kubenodes:
                if target["ip"] != source_ip:
                    for port_info in _KUBE_TO_KUBE_PORTS:
                        test_pairs.append((target, port_info))
        else:
            # Datanode -> every other datanode on replication/gossip ports
            for target in datanodes:
                if target["ip"] != source_ip:
                    for port_info in _DATA_TO_DATA_PORTS:
                        test_pairs.append((target, port_info))

        # Handle the edge case where no tests apply (e.g. single-node cluster)
        if not test_pairs:
            self._health_info = f"No port tests applicable for {source_name}"
            return "0/0 open"

        self.terminal.step(
            f"Testing {len(test_pairs)} port(s) from {source_name}..."
        )

        # Batch all port tests into a single shell command separated by semicolons
        # so we only open one SSH connection per source host
        command_parts: list[str] = [
            _build_port_test_command(target["ip"], int(port_info["port"]))
            for target, port_info in test_pairs
        ]
        batch_command: str = "; ".join(command_parts)

        # Execute the batched command on the source host
        result = self.run_ssh(source_ip, batch_command)

        # Parse the output each line is "PORT <ip> <port> OPEN|CLOSED"
        output_lines: list[str] = result.stdout.strip().splitlines()
        output_lookup: dict[str, str] = {}
        for line in output_lines:
            stripped: str = line.strip()
            if stripped.startswith("PORT "):
                parts: list[str] = stripped.split()
                if len(parts) >= 4:
                    # Key by "ip:port" for easy lookup
                    lookup_key: str = f"{parts[1]}:{parts[2]}"
                    output_lookup[lookup_key] = parts[3]

        # Build detailed per-port results for metadata
        port_results: list[dict[str, Any]] = []
        open_count: int = 0
        total_count: int = len(test_pairs)

        for target, port_info in test_pairs:
            target_ip: str = target["ip"]
            port: int = int(port_info["port"])
            service: str = str(port_info["service"])
            lookup_key = f"{target_ip}:{port}"

            # Determine status from output default to "filtered" if no output
            raw_status: str = output_lookup.get(lookup_key, "FILTERED")
            status: str = "open" if raw_status == "OPEN" else ("closed" if raw_status == "CLOSED" else "filtered")

            if status == "open":
                open_count += 1

            # Determine node types from name prefixes for downstream diagram rendering
            source_type: str = "kubenode" if is_kubenode else "datanode"
            target_type: str = "kubenode" if target["name"].startswith("kubenode-") else "datanode"

            port_results.append({
                "source_name": source_name,
                "source_ip": source_ip,
                "source_type": source_type,
                "target_name": target["name"],
                "target_ip": target_ip,
                "target_type": target_type,
                "port": port,
                "protocol": "tcp",
                "service": service,
                "status": status,
            })

        # Store detailed results in metadata the per_host_target base class
        # merges this into the DataPoint metadata automatically
        self._health_info = None
        if open_count == total_count:
            self._health_info = f"All {total_count} ports open from {source_name}"
        else:
            # List the closed and filtered ports separately for quick diagnosis
            closed: list[str] = [
                f"{r['target_name']}:{r['port']} ({r['service']})"
                for r in port_results if r["status"] == "closed"
            ]
            filtered: list[str] = [
                f"{r['target_name']}:{r['port']} ({r['service']})"
                for r in port_results if r["status"] == "filtered"
            ]
            health_parts: list[str] = []
            if closed:
                health_parts.append(f"closed: {', '.join(closed)}")
            if filtered:
                health_parts.append(f"filtered: {', '.join(filtered)}")
            self._health_info = (
                f"{open_count}/{total_count} open from {source_name}, "
                f"{'; '.join(health_parts)}"
            )

        # Attach structured port results to the DataPoint via _track_output
        # so both raw_output and metadata.commands are populated consistently.
        self._track_output("port_results_json", f"PORT_RESULTS_JSON:{_serialize_port_results(port_results)}")

        return f"{open_count}/{total_count} open"

    def description_for_host(self, host: dict[str, str]) -> str:
        """Return a per-host label for display in results.

        Args:
            host: Dict with 'name' and 'ip' keys.

        Returns:
            Human-readable string identifying this host's measurement.
        """
        return f"Port connectivity from {host['name']} ({host['ip']})"


def _serialize_port_results(port_results: list[dict[str, Any]]) -> str:
    """Serialize port results to a JSON-like string for raw output.

    Uses stdlib json for reliable serialization rather than hand-formatting,
    keeping the raw_output machine-parseable for downstream consumers.

    Args:
        port_results: List of per-port result dicts.

    Returns:
        JSON string of the port results array.
    """
    # Import here to avoid polluting the module-level namespace for a
    # serialization-only utility
    import json
    return json.dumps(port_results)
