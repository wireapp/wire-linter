"""Checks node pressure conditions (memory, disk, PID).

A node can report Ready but still have pressure conditions active.
Memory pressure triggers pod evictions. Disk pressure prevents new
pods from scheduling. PID pressure means the node is running out of
process IDs. These are early warning signs before a node goes NotReady.

Produces a single data point at « kubernetes/nodes/pressure_conditions ».
Value is a JSON string with per-node pressure status.
"""

from __future__ import annotations

import json
from typing import Any

# Ours
from src.lib.base_target import BaseTarget


class NodePressureConditions(BaseTarget):
    """Checks memory, disk, and PID pressure conditions on all nodes.

    A node with pressure conditions active is at risk of evicting pods
    or becoming NotReady. These are early warning signs.
    """

    @property
    def description(self) -> str:
        """Human-readable description of what this target collects."""
        return "Node pressure conditions (memory, disk, PID)"

    @property
    def explanation(self) -> str:
        """Why this target exists and what it's used for."""
        return (
            "Nodes can be Ready but still under memory, disk, or PID pressure. "
            "Pressure conditions trigger pod evictions and are early warning signs "
            "before a node goes completely NotReady."
        )

    def collect(self) -> str:
        """Fetch node conditions and extract pressure flags.

        Returns:
            JSON string with per-node pressure status.
        """
        self.terminal.step("Checking node pressure conditions...")

        _result, parsed = self.run_kubectl("nodes")

        node_details: list[dict[str, Any]] = []
        nodes_with_pressure: int = 0
        total_nodes: int = 0

        if isinstance(parsed, dict):
            for node in parsed.get("items", []):
                total_nodes += 1
                node_name: str = node.get("metadata", {}).get("name", "unknown")
                conditions: list[dict[str, Any]] = (
                    node.get("status", {}).get("conditions", [])
                )

                # Extract pressure conditions (True = under pressure)
                pressure: dict[str, bool] = {
                    "memory_pressure": False,
                    "disk_pressure": False,
                    "pid_pressure": False,
                    "network_unavailable": False,
                }

                for condition in conditions:
                    ctype: str = condition.get("type", "")
                    status: str = condition.get("status", "")
                    is_true: bool = status == "True"

                    if ctype == "MemoryPressure":
                        pressure["memory_pressure"] = is_true
                    elif ctype == "DiskPressure":
                        pressure["disk_pressure"] = is_true
                    elif ctype == "PIDPressure":
                        pressure["pid_pressure"] = is_true
                    elif ctype == "NetworkUnavailable":
                        pressure["network_unavailable"] = is_true

                has_any_pressure: bool = any(pressure.values())
                if has_any_pressure:
                    nodes_with_pressure += 1

                node_details.append({
                    "name": node_name,
                    **pressure,
                    "has_pressure": has_any_pressure,
                })

        if nodes_with_pressure == 0:
            self._health_info = f"No pressure on any of {total_nodes} node(s)"
        else:
            self._health_info = (
                f"{nodes_with_pressure}/{total_nodes} node(s) under pressure"
            )

        return json.dumps({
            "total_nodes": total_nodes,
            "nodes_with_pressure": nodes_with_pressure,
            "details": node_details,
        }, sort_keys=True)
