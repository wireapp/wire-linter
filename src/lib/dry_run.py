"""Dry-run command recording and table display.

When the runner is invoked with --dry-run, no commands are actually executed.
Instead, each execution method records what it would have done, and at the
end the runner prints a table showing all commands that would have been run,
along with where each command would execute (local, SSH, jump hosts, etc.).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field


@dataclass
class CommandRecord:
    """A command that would be executed in a normal (non dry-run) run.

    Attributes:
        target_path: Which target requested this command
            (e.g. 'databases/cassandra/cluster_status').
        command: The actual command or query that would run
            (e.g. 'nodetool status', 'kubectl get pods -n wire -o json').
        execution_type: Category of execution method
            ('local', 'ssh', 'kubectl', 'db-ssh', 'cql', 'http', 'http-via-ssh').
        hops: Ordered list describing the execution path. Each element is one
            step in the chain, e.g. ['ssh deploy@10.0.0.1', 'ssh root@192.168.1.5'].
            A single-element list with 'local' means the command runs on this machine.
    """

    target_path: str
    command: str
    execution_type: str
    hops: list[str] = field(default_factory=lambda: ["local"])


def format_dry_run_table(records: list[CommandRecord], use_color: bool = True) -> str:
    """Format all recorded commands as a two-line-per-row table.

    Layout:
        Target                              Command
        ───────────────────────────────     ──────────────────────────────────────
        databases/cassandra/cluster_status  via: ssh demo@10.0.0.1 → ssh root@db1
                                            cmd: nodetool status
        kubernetes/nodes/ready              via: local (docker run wire-deploy...)
                                            cmd: kubectl get nodes -o json

    Each row has the target name in the left column, and two lines in the right
    column: the routing/hops line (grey, prefixed with «via:») and the actual
    command line (prefixed with «cmd:»).

    Args:
        records: All command records from the dry-run execution.
        use_color: Whether to use ANSI color codes in output.

    Returns:
        Formatted multi-line table string ready for printing.
    """
    if not records:
        return "  No commands would be executed for this configuration."

    # ANSI codes
    bold: str = "\033[1m" if use_color else ""
    gray: str = "\033[90m" if use_color else ""
    cyan: str = "\033[36m" if use_color else ""
    reset: str = "\033[0m" if use_color else ""

    # Determine target column width from content
    target_width: int = len("Target")
    for record in records:
        target_width = max(target_width, len(record.target_path))

    # Cap target width and compute command column width
    term_width: int = shutil.get_terminal_size((120, 24)).columns
    gap: int = 3
    target_cap: int = 42
    target_width = min(target_width, target_cap)
    cmd_col_width: int = max(30, term_width - target_width - gap - 2)

    lines: list[str] = []

    # Header
    lines.append(
        f"  {bold}{'Target'.ljust(target_width)}{' ' * gap}{'Command'}{reset}"
    )

    # Separator
    horiz: str = '\u2500'
    target_sep: str = horiz * target_width
    cmd_sep: str = horiz * cmd_col_width
    lines.append(
        f"  {gray}{target_sep}{' ' * gap}{cmd_sep}{reset}"
    )

    # Blank left column for the second line of each row
    blank_left: str = " " * target_width

    for record in records:
        # Build the hops/routing line
        hops_display: str = " \u2192 ".join(record.hops)

        # Truncate if needed
        target_display: str = record.target_path
        if len(target_display) > target_width:
            target_display = target_display[: target_width - 2] + ".."

        cmd_display: str = record.command
        if len(cmd_display) > cmd_col_width - 6:
            cmd_display = cmd_display[: cmd_col_width - 8] + ".."

        hops_truncated: str = hops_display
        if len(hops_truncated) > cmd_col_width - 6:
            hops_truncated = hops_truncated[: cmd_col_width - 8] + ".."

        # Line 1: target name + routing (grey)
        lines.append(
            f"  {cyan}{target_display.ljust(target_width)}{reset}"
            f"{' ' * gap}"
            f"{gray}via: {hops_truncated}{reset}"
        )

        # Line 2: blank left + actual command
        lines.append(
            f"  {blank_left}"
            f"{' ' * gap}"
            f"cmd: {cmd_display}"
        )

    return "\n".join(lines)
