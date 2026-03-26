"""Collects firewall rules from each cluster node.

SSHes into every kubenode and datanode to dump active firewall rules.
Detects which firewall system is running (iptables, nftables, ufw,
firewalld) and captures the full ruleset. Used to diagnose blocked
inter-node traffic that port_connectivity.py flags.

Related modules:
    src/lib/vm_hosts.py            shared host discovery
    src/lib/per_host_target.py     base class for per-host iteration
    src/targets/network/port_connectivity.py tests the ports these rules affect
"""

from __future__ import annotations

from typing import Any

# Ours
from src.lib.per_host_target import PerHostTarget
from src.lib.vm_hosts import discover_vm_hosts


# Firewall tools to check, in priority order. Whichever produces output first
# is marked as « active ». We always run all of them to get the full picture.
_FIREWALL_COMMANDS: list[dict[str, str]] = [
    {
        "name": "nftables",
        "command": "sudo nft list ruleset 2>/dev/null",
    },
    {
        "name": "iptables",
        "command": "sudo iptables-save 2>/dev/null",
    },
    {
        "name": "ufw",
        "command": "sudo ufw status verbose 2>/dev/null",
    },
    {
        "name": "firewalld",
        "command": "sudo firewall-cmd --list-all-zones 2>/dev/null",
    },
]


def _count_rules(firewall_type: str, output: str) -> int:
    """Count firewall rules from raw command output.

    Each firewall tool has its own output format, so we count rule lines
    differently depending on the tool.

    Args:
        firewall_type: One of « nftables », « iptables », « ufw », « firewalld ».
        output:        Raw command output to parse.

    Returns:
        Rule count as an integer.
    """
    lines: list[str] = output.strip().splitlines()

    if firewall_type == "iptables":
        # iptables-save: lines starting with -A are rules, skip comments/headers
        return sum(1 for line in lines if line.startswith("-A "))

    if firewall_type == "nftables":
        # nft spits out rules with action keywords like accept, drop, etc.
        rule_keywords: list[str] = ["accept", "drop", "reject", "counter", "jump", "goto", "masquerade", "snat", "dnat"]
        count: int = 0
        for line in lines:
            stripped: str = line.strip().lower()
            # Skip empty lines, braces, and table/chain headers
            if not stripped or stripped in ("{", "}"):
                continue
            # Skip chain policy declarations (e.g. "type filter hook input priority filter; policy accept;")
            # These contain "hook" and are not individual firewall rules
            if "hook" in stripped:
                continue
            if any(keyword in stripped for keyword in rule_keywords):
                count += 1
        return count

    if firewall_type == "ufw":
        # ufw status verbose: rules start after the header dashes
        count = 0
        in_rules: bool = False
        for line in lines:
            if line.startswith("--"):
                in_rules = True
                continue
            if in_rules and line.strip():
                count += 1
        return count

    if firewall_type == "firewalld":
        # Count lines with « rule » or « ports: » keywords
        return sum(
            1 for line in lines
            if "rule " in line.lower() or "ports:" in line.lower()
        )

    return 0


class FirewallRules(PerHostTarget):
    """Collects firewall rules and detects which firewall is running on each host.

    Runs all four major Linux firewall tools (iptables-save, nft, ufw,
    firewall-cmd) on each host with sudo. Whichever produces output is
    the active firewall.
    """

    @property
    def description(self) -> str:
        """Short label for this check."""
        return "Firewall rules"

    @property
    def explanation(self) -> str:
        """Why we check this."""
        return (
            "Bad firewall rules silently block inter-node traffic. "
            "We pull the full ruleset from each host to debug connectivity "
            "issues that port_connectivity finds."
        )

    def get_hosts(self) -> list[dict[str, str]]:
        """Return all cluster hosts (kubenodes + datanodes).

        Same host discovery as port_connectivity for consistency.

        Returns:
            List of host dicts with « name » and « ip » keys.
        """
        return discover_vm_hosts(self.config, self.run_kubectl)

    def collect_for_host(self, host: dict[str, str]) -> str:
        """SSH into the host and grab firewall rules from all tools.

        Runs iptables-save, nft list ruleset, ufw status, and firewall-cmd
        in sequence. Prefixed with sudo, stderr suppressed so missing tools
        don't error out.

        Args:
            host: Dict with « name » and « ip » keys.

        Returns:
            Detected firewall type (« nftables », « iptables », « none », etc).
        """
        host_name: str = host["name"]
        host_ip: str = host["ip"]

        self.terminal.step(f"Collecting firewall rules from {host_name}...")

        # Whichever tool produces output first is the active firewall
        detected_type: str = "none"
        total_rule_count: int = 0
        collected_outputs: dict[str, str] = {}

        for fw_tool in _FIREWALL_COMMANDS:
            tool_name: str = fw_tool["name"]
            tool_command: str = fw_tool["command"]

            self.terminal.step(f"Checking {tool_name} on {host_name}...")

            # Run the firewall command on the remote host
            result = self.run_ssh(host_ip, tool_command)

            output: str = result.stdout.strip()

            # Non-empty output means the tool is present and has rules
            if output:
                collected_outputs[tool_name] = output

                # First tool with output is the active one
                if detected_type == "none":
                    detected_type = tool_name
                    total_rule_count = _count_rules(tool_name, output)

        # Build health summary
        if detected_type == "none":
            self._health_info = f"No firewall detected on {host_name}"
        else:
            detected_tools: list[str] = list(collected_outputs.keys())
            if len(detected_tools) == 1:
                self._health_info = (
                    f"{detected_type} active on {host_name}, "
                    f"{total_rule_count} rules"
                )
            else:
                # Multiple firewall systems on one host is confusing and worth flagging
                self._health_info = (
                    f"{detected_type} active on {host_name} "
                    f"({total_rule_count} rules), "
                    f"also found: {', '.join(t for t in detected_tools if t != detected_type)}"
                )

        return detected_type

    def description_for_host(self, host: dict[str, str]) -> str:
        """Per-host label for the results.

        Args:
            host: Dict with « name » and « ip » keys.

        Returns:
            String identifying this host's measurement.
        """
        return f"Firewall rules on {host['name']} ({host['ip']})"
