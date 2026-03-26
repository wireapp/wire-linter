"""Kubectl command wrapper that executes kubectl commands and parses JSON output.
Supports running kubectl either locally or remotely via SSH on the admin host
(for deployments where kubectl isn't available locally).

For Wire offline deployments, kubectl lives inside a Docker container (wire-server-deploy
image). When docker_image is provided, commands get wrapped in
«docker run --rm --network=host ... <image> kubectl <args>».
"""

from __future__ import annotations

import json
import shlex
from typing import Any, TYPE_CHECKING

from src.lib.command import run_command, CommandResult

if TYPE_CHECKING:
    from src.lib.ssh import SSHTarget


def int_or_zero(d: dict[str, Any], key: str) -> int:
    """Extract an integer value from a dict, treating None as 0.

    Python's dict.get(key, default) only uses the default when the key is
    absent — if the key is present with value None (common in Kubernetes
    status fields like readyReplicas: null), get() returns None. This
    helper coalesces both missing and None values to 0.

    Args:
        d: The dict to read from.
        key: The key to look up.

    Returns:
        The integer value, or 0 if the key is absent or its value is None.
    """
    value: Any = d.get(key)
    if value is None:
        return 0
    # Coerce to int — Kubernetes may return floats (e.g. 3.0) or strings
    # in unexpected payloads; int() handles both safely
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _build_kubectl_parts(
    args: list[str],
    context: str = "",
) -> list[str]:
    """Build the kubectl command argument list.

    Args:
        args: kubectl subcommand and arguments (e.g., ['get', 'nodes', '-o', 'json']).
        context: Kubernetes context to use (empty = current context).

    Returns:
        Complete command parts starting with «kubectl».
    """
    parts: list[str] = ['kubectl']

    # context flag goes right after kubectl, before the subcommand
    if context:
        parts.extend(['--context', context])

    parts.extend(args)
    return parts


def _wrap_in_docker(
    parts: list[str],
    docker_image: str,
    admin_home: str,
) -> list[str]:
    """Wrap a kubectl command in a docker run invocation.

    Wire offline deployments run kubectl inside the wire-server-deploy Docker image.
    This constructs the «docker run» prefix with required volume mounts and network settings.

    Args:
        parts: kubectl command parts (e.g., ['kubectl', 'get', 'nodes']).
        docker_image: Full Docker image name:tag.
        admin_home: Home directory of the admin user on the remote host.

    Returns:
        New command parts with docker run prefix.
    """
    docker_parts: list[str] = [
        'docker', 'run', '--rm',
        # host networking so kubectl can reach the k8s API
        '--network=host',
        # mount SSH keys so kubectl can authenticate
        '-v', f'{admin_home}/.ssh:/root/.ssh',
        # mount wire-server-deploy for kubeconfig and other config
        '-v', f'{admin_home}/wire-server-deploy:/wire-server-deploy',
        # the Wire container image
        docker_image,
    ]
    # append the original kubectl command parts
    docker_parts.extend(parts)
    return docker_parts


def kubectl_get(
    resource: str,
    namespace: str | None = None,
    selector: str | None = None,
    all_namespaces: bool = False,
    timeout: int = 30,
    context: str = "",
    ssh_target: 'SSHTarget | None' = None,
    docker_image: str = "",
    admin_home: str = "",
) -> tuple[CommandResult, dict[str, Any] | None]:
    """Run kubectl get and parse the JSON output.

    Args:
        resource: The resource type and optional name (e.g., 'nodes', 'pods/my-pod').
        namespace: Kubernetes namespace. Ignored if all_namespaces is True.
        selector: Label selector (e.g., 'app=brig').
        all_namespaces: If True, search across all namespaces.
        timeout: Command timeout in seconds.
        context: Kubernetes context to use. Empty string = current context.
        ssh_target: Optional SSHTarget for remote execution. None = run locally.
        docker_image: Docker image for running kubectl. Empty = run kubectl directly.
        admin_home: Admin user's home dir on the remote host (for Docker volume mounts).

    Returns:
        A tuple of (CommandResult, parsed_json). parsed_json is None if
        the command failed, output couldn't be parsed, or the parsed
        result was not a dict (kubectl -o json should always return a dict).
    """
    # Build kubectl subcommand arguments
    kubectl_args: list[str] = ['get', resource, '-o', 'json']

    # all_namespaces takes precedence over namespace
    if all_namespaces:
        kubectl_args.append('--all-namespaces')
    elif namespace is not None:
        kubectl_args.extend(['-n', namespace])

    # Add label selector if provided
    if selector is not None:
        kubectl_args.extend(['-l', selector])

    # Build the full kubectl command
    parts: list[str] = _build_kubectl_parts(kubectl_args, context=context)

    # Wrap in docker if image is specified
    if docker_image:
        parts = _wrap_in_docker(parts, docker_image, admin_home)

    # Execute locally or via SSH
    if ssh_target is not None:
        # Quote each part so spaces/metacharacters survive the remote shell
        command_str: str = ' '.join(shlex.quote(p) for p in parts)
        result: CommandResult = ssh_target.run(command_str, timeout=timeout)
    else:
        result = run_command(parts, timeout=timeout)

    # Skip parsing if stdout is empty to avoid confusing JSONDecodeError
    if not result.stdout.strip():
        return (result, None)

    # Attempt to parse JSON output regardless of exit code
    try:
        parsed_data: Any = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        # JSON parsing failed return raw result with None for parsed data
        return (result, None)

    # kubectl -o json should always return a dict; if json.loads produced
    # a non-dict type (list, string, number) the output is unexpected so
    # treat it the same as a parse failure to prevent AttributeError in callers
    if not isinstance(parsed_data, dict):
        return (result, None)

    return (result, parsed_data)


def kubectl_raw(
    args: list[str],
    timeout: int = 30,
    context: str = "",
    ssh_target: 'SSHTarget | None' = None,
    docker_image: str = "",
    admin_home: str = "",
) -> CommandResult:
    """Run an arbitrary kubectl command.

    For commands that don't support -o json (like 'kubectl top').

    Args:
        args: kubectl arguments (e.g., ['top', 'nodes']).
        timeout: Command timeout in seconds.
        context: Kubernetes context to use.
        ssh_target: Optional SSHTarget for remote execution. None = run locally.
        docker_image: Docker image for running kubectl. Empty = run kubectl directly.
        admin_home: Admin user's home dir on the remote host (for Docker volume mounts).

    Returns:
        A CommandResult.
    """
    # Build the full kubectl command
    parts: list[str] = _build_kubectl_parts(args, context=context)

    # Wrap in docker if image is specified
    if docker_image:
        parts = _wrap_in_docker(parts, docker_image, admin_home)

    # Execute locally or via SSH
    if ssh_target is not None:
        # Quote each part so spaces/metacharacters survive the remote shell
        command_str: str = ' '.join(shlex.quote(p) for p in parts)
        return ssh_target.run(command_str, timeout=timeout)

    return run_command(parts, timeout=timeout)


def detect_kubectl_docker_image(ssh_target: 'SSHTarget') -> str:
    """Auto-detect the wire-server-deploy Docker image on the admin host.

    SSHes to the admin host and lists Docker images matching the
    wire-server-deploy pattern. Returns the first match.

    Args:
        ssh_target: SSHTarget connected to the admin host.

    Returns:
        The full image name:tag string, or empty string if not found.
    """
    # List docker images matching the wire-server-deploy pattern
    result: CommandResult = ssh_target.run(
        "docker images --format '{{.Repository}}:{{.Tag}}' | grep wire-server-deploy | head -1"
    )

    # Return the image name if found, empty string otherwise
    image: str = result.stdout.strip()
    if result.success and image:
        return image
    return ""


def detect_kubectl_docker_image_local() -> str:
    """Auto-detect the wire-server-deploy Docker image locally.

    Same logic as detect_kubectl_docker_image() but runs the docker command
    on the local machine instead of over SSH. Used when --source admin-host
    means we're already on the machine that has the Docker image.

    Returns:
        The full image name:tag string, or empty string if not found.
    """
    # List docker images matching the wire-server-deploy pattern
    result: CommandResult = run_command(
        ['sh', '-c', "docker images --format '{{.Repository}}:{{.Tag}}' | grep wire-server-deploy | head -1"],
        timeout=15,
    )

    # Return the image name if found, empty string otherwise
    image: str = result.stdout.strip()
    if result.success and image:
        return image
    return ""
