"""SSH command builder with optional jump-host support and tunneling.

Chains together SSH commands on remote hosts:

    ssh = SSH(config)

    # Direct SSH to a host
    result = ssh.to("10.0.0.1").run("uptime")

    # SSH via a jump host to reach a private network host
    result = ssh.via("admin.example.com").to("192.168.122.220").run("nodetool status")

    # SSH tunnel for local port forwarding
    with SSHTunnel(local_port=19042, remote_host="192.168.122.220",
                   remote_port=9042, ...) as tunnel:
        # Connect to localhost:19042 to reach 192.168.122.220:9042
        ...

When a jump host is used, we build a nested SSH command the outer SSH goes
to the jump host using admin credentials, then an inner SSH from there reaches
the target using database credentials. Lets us reach private network hosts
behind the admin host.

Classes:
    SSH        Entry point with config, provides .to() and .via().
    SSHJump    After .via(), waiting for .to() to set the target.
    SSHTarget  Ready to .run() a command.
    SSHTunnel  Local port forwarding via SSH.

Connections:
    src/lib/command.py run_command and CommandResult.
    src/lib/config.py  Config with SSH credentials.
    Used by BaseTarget helpers and http_client.py.
"""

from __future__ import annotations

import dataclasses
import shlex
import socket
import subprocess
import time
from typing import TYPE_CHECKING

from src.lib.command import run_command, CommandResult

if TYPE_CHECKING:
    from src.lib.config import Config


class SSHTarget:
    """Ready to run a command on the target host.

    Created by SSH.to() or SSHJump.to(). Call .run() to execute.
    """

    def __init__(
        self,
        host: str,
        user: str,
        key: str,
        port: int,
        timeout: int,
        jump_host: str | None = None,
        jump_user: str | None = None,
        jump_key: str | None = None,
        jump_port: int | None = None,
    ) -> None:
        """Store target and optional jump host details."""
        self._host: str = host
        self._user: str = user
        self._key: str = key
        self._port: int = port
        self._timeout: int = timeout
        self._jump_host: str | None = jump_host
        self._jump_user: str | None = jump_user
        self._jump_key: str | None = jump_key
        self._jump_port: int | None = jump_port

    def _strip_known_hosts_warning(self, result: CommandResult) -> CommandResult:
        """Filter out the 'Permanently added X to known hosts' lines.

        SSH logs this even with UserKnownHostsFile=/dev/null. We skip host key
        verification anyway, so it's noise.
        """
        filtered_lines: list[str] = [
            line for line in result.stderr.splitlines()
            if 'Permanently added' not in line or 'known hosts' not in line
        ]
        return dataclasses.replace(result, stderr='\n'.join(filtered_lines))

    def run(self, command: str, timeout: int | None = None) -> CommandResult:
        """Run a command on the target host.

        If a jump host was set, uses nested SSH outer to the jump host,
        inner from there to the target. Otherwise direct connection.

        Args:
            command: Shell command to execute on the remote host.
            timeout: Override the timeout for this specific command in seconds.
                     None means use the SSHTarget's configured default timeout.
        """
        # Resolve which timeout to use — caller override takes precedence
        effective_timeout: int = timeout if timeout is not None else self._timeout
        if self._jump_host:
            return self._strip_known_hosts_warning(self._run_via_jump(command, effective_timeout))
        return self._strip_known_hosts_warning(self._run_direct(command, effective_timeout))

    def _run_direct(self, command: str, timeout: int) -> CommandResult:
        """Direct SSH to the target host."""
        ssh_cmd: list[str] = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10',
            '-i', self._key,
            '-p', str(self._port),
            f'{self._user}@{self._host}',
            command,
        ]
        return run_command(ssh_cmd, timeout=timeout)

    def _run_via_jump(self, command: str, timeout: int) -> CommandResult:
        """Nested SSH outer to jump host, inner from there to target.

        Inner SSH runs on the jump host's shell, using the database key
        that lives on the jump host.
        """
        # Inner SSH command runs on the jump host, reaches the target
        inner_ssh: str = (
            f"ssh"
            f" -o StrictHostKeyChecking=no"
            f" -o UserKnownHostsFile=/dev/null"
            f" -o BatchMode=yes"
            f" -o ConnectTimeout=10"
            f" -i {shlex.quote(self._key)}"
            f" -p {self._port}"
            f" {self._user}@{self._host}"
            f" {shlex.quote(command)}"
        )

        # Outer SSH command connects to the jump host from the local machine
        outer_cmd: list[str] = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10',
            '-i', self._jump_key or '',
            '-p', str(self._jump_port or 22),
            f'{self._jump_user}@{self._jump_host}',
            inner_ssh,
        ]
        return run_command(outer_cmd, timeout=timeout)


class SSHJump:
    """Intermediate jump host is set, waiting for .to(target).

    Created by SSH.via(). Holds jump host info and config for the
    inner-hop credentials.
    """

    def __init__(self, config: 'Config', jump_host: str) -> None:
        """Store config and the jump host to route through."""
        self._config: Config = config
        self._jump_host: str = jump_host

    def to(self, host: str) -> SSHTarget:
        """Set the final target host (reached via the jump host).

        Jump host uses admin_host credentials.
        Target uses database credentials.
        """
        db: object = self._config.databases
        return SSHTarget(
            # Target credentials for the inner hop (jump host → target)
            host=host,
            user=db.ssh_user,
            key=db.ssh_key,
            port=db.ssh_port,
            timeout=self._config.timeout,
            # Jump credentials for the outer hop (local → jump host)
            jump_host=self._jump_host,
            jump_user=self._config.admin_host.user,
            jump_key=self._config.admin_host.ssh_key,
            jump_port=self._config.admin_host.ssh_port,
        )


class SSH:
    """SSH command builder entry point for all SSH operations.

    Created once from a Config object, then used to execute commands
    on remote hosts.

    Usage:
        ssh = SSH(config)

        # Direct SSH to admin host
        result = ssh.to("admin.example.com").run("kubectl get pods")

        # SSH via admin host to private database VM
        result = ssh.via("admin.example.com").to("192.168.122.220").run("nodetool status")
    """

    def __init__(self, config: 'Config') -> None:
        """Store the config for SSH operations."""
        self._config: Config = config

    def to(self, host: str) -> SSHTarget:
        """Direct SSH to a host using admin_host credentials."""
        return SSHTarget(
            host=host,
            user=self._config.admin_host.user,
            key=self._config.admin_host.ssh_key,
            port=self._config.admin_host.ssh_port,
            timeout=self._config.timeout,
        )

    def db_to(self, host: str) -> SSHTarget:
        """Direct SSH to a host using database credentials.

        Use this when the gatherer runs on the admin host the database
        SSH key is local, so we connect directly without jumping.
        """
        db: object = self._config.databases
        return SSHTarget(
            host=host,
            user=db.ssh_user,
            key=db.ssh_key,
            port=db.ssh_port,
            timeout=self._config.timeout,
        )

    def via(self, jump_host: str) -> SSHJump:
        """Route through a jump host to reach hosts on a private network.

        Jump host uses admin_host credentials. Target (via .to()) uses
        database credentials.
        """
        return SSHJump(config=self._config, jump_host=jump_host)


def _find_free_port() -> int:
    """Find a free TCP port by binding to port 0.

    OS assigns an ephemeral port which we release right away. Small race
    window, but fine for short-lived tunnels.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class SSHTunnel:
    """SSH local port forwarding as a context manager.

    Forwards a local port to a remote host:port, optionally through a
    jump host. Tunnel runs as a background subprocess, torn down on exit.

    Usage (direct SSH host can reach target):
        with SSHTunnel(
            remote_host="10.0.0.10", remote_port=9042,
            ssh_host="admin.example.com", ssh_user="deploy",
            ssh_key="/path/to/key", ssh_port=22,
        ) as tunnel:
            # Connect to localhost:tunnel.local_port -> 10.0.0.10:9042
            ...

    Usage (via jump target is behind private network):
        with SSHTunnel(
            remote_host="192.168.122.220", remote_port=9042,
            ssh_host="admin.example.com", ssh_user="deploy",
            ssh_key="/path/to/key", ssh_port=22,
            jump_host="admin.example.com", jump_user="deploy",
            jump_key="/path/to/key", jump_port=22,
        ) as tunnel:
            ...
    """

    def __init__(
        self,
        remote_host: str,
        remote_port: int,
        ssh_host: str,
        ssh_user: str,
        ssh_key: str,
        ssh_port: int = 22,
        jump_host: str | None = None,
        jump_user: str | None = None,
        jump_key: str | None = None,
        jump_port: int | None = None,
        local_port: int = 0,
        timeout: float = 10.0,
    ) -> None:
        """Store tunnel configuration (doesn't open yet)."""
        self._remote_host: str = remote_host
        self._remote_port: int = remote_port
        self._ssh_host: str = ssh_host
        self._ssh_user: str = ssh_user
        self._ssh_key: str = ssh_key
        self._ssh_port: int = ssh_port
        self._jump_host: str | None = jump_host
        self._jump_user: str | None = jump_user
        self._jump_key: str | None = jump_key
        self._jump_port: int | None = jump_port
        self._local_port: int = local_port or _find_free_port()
        self._timeout: float = timeout
        self._proc: subprocess.Popen[bytes] | None = None

    @property
    def local_port(self) -> int:
        """Local port that forwards to the remote target."""
        return self._local_port

    def open(self) -> None:
        """Start the SSH tunnel subprocess and wait until ready.

        Launches ssh -L in the background, polls the local port until it
        accepts connections or timeout.

        Raises:
            RuntimeError: If the tunnel fails to start within the timeout.
        """
        forward_spec: str = f"{self._local_port}:{self._remote_host}:{self._remote_port}"

        cmd: list[str] = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10',
            '-N',
            '-L', forward_spec,
            '-i', self._ssh_key,
            '-p', str(self._ssh_port),
        ]

        if self._jump_host:
            proxy_cmd: str = (
                f"ssh -o StrictHostKeyChecking=no"
                f" -o UserKnownHostsFile=/dev/null"
                f" -o BatchMode=yes"
                f" -o ConnectTimeout=10"
                f" -i {shlex.quote(self._jump_key or '')}"
                f" -p {self._jump_port or 22}"
                f" -W %h:%p"
                f" {self._jump_user}@{self._jump_host}"
            )
            cmd.extend(['-o', f'ProxyCommand={proxy_cmd}'])

        cmd.append(f'{self._ssh_user}@{self._ssh_host}')

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        deadline: float = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                stderr_output: str = (self._proc.stderr.read() or b'').decode('utf-8', errors='replace')
                raise RuntimeError(
                    f"SSH tunnel exited with code {self._proc.returncode}: {stderr_output.strip()}"
                )

            try:
                probe: socket.socket = socket.create_connection(
                    ('127.0.0.1', self._local_port), timeout=0.5,
                )
                probe.close()
                return
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)
        self.close()
        raise RuntimeError(
            f"SSH tunnel to {self._remote_host}:{self._remote_port} "
            f"did not become ready within {self._timeout}s"
        )

    def close(self) -> None:
        """Terminate the SSH tunnel subprocess."""
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self._proc.kill()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            self._proc = None

    def __enter__(self) -> SSHTunnel:
        """Context manager open the tunnel."""
        self.open()
        return self

    def __exit__(self, *_args: object) -> None:
        """Context manager close the tunnel."""
        self.close()
