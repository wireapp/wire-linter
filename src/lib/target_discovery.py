"""Discovers target classes by scanning the filesystem under src/targets/.

Target paths come directly from file paths no registry needed. Each .py file
under src/targets/ should have exactly one BaseTarget subclass. The discovery
system finds it automatically and the runner executes it through the standard
lifecycle.

Supports glob-style filtering for the --target parameter.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import inspect
import os
import sys
from dataclasses import dataclass
from typing import Any

from src.lib.base_target import BaseTarget
from src.lib.iterable_target import IterableTarget
from src.lib.per_configmap_target import PerConfigmapTarget
from src.lib.per_host_target import PerHostTarget
from src.lib.per_service_target import PerServiceTarget


class TargetDiscoveryError(Exception):
    """Raised when target discovery fails import errors, invalid files, etc."""


@dataclass
class DiscoveredTarget:
    """A discovered target, ready to instantiate."""

    path: str  # e.g., 'databases/cassandra/cluster_status'
    module_path: str  # e.g., 'src.targets.databases.cassandra.cluster_status'
    target_class: type  # Class to instantiate
    is_per_host: bool  # Is this an IterableTarget subclass (produces multiple results)?


# ---------------------------------------------------------------------------
# Optional target registration decorator
# ---------------------------------------------------------------------------

# Global registry for explicitly registered targets. Keyed by path so
# duplicates are detected. Filesystem scanning remains the primary mechanism;
# registration provides an opt-in alternative for targets that need explicit
# paths, grouping, or metadata beyond what the filesystem implies.
_registered_targets: dict[str, type] = {}


def register_target(path: str) -> Any:
    """Decorator to explicitly register a target class with a given path.

    Usage:
        @register_target("databases/cassandra/cluster_status")
        class ClusterStatus(BaseTarget):
            ...

    When discover_targets() runs, registered targets are included alongside
    filesystem-discovered ones. If the same path appears in both, the
    registered version takes precedence. This allows helper files to live
    in src/targets/ without being accidentally imported as targets.

    Args:
        path: The hierarchical target path (e.g. 'databases/cassandra/cluster_status').

    Returns:
        A class decorator that registers the target and returns it unchanged.
    """
    def decorator(cls: type) -> type:
        if path in _registered_targets:
            existing: str = _registered_targets[path].__name__
            raise TargetDiscoveryError(
                f"Duplicate target registration for path '{path}': "
                f"{cls.__name__} conflicts with {existing}"
            )
        _registered_targets[path] = cls
        return cls

    return decorator


def get_registered_targets() -> dict[str, type]:
    """Return a copy of the registered targets dict.

    Returns:
        Dict mapping path strings to target classes.
    """
    return dict(_registered_targets)


def clear_registered_targets() -> None:
    """Clear all registered targets. Used in tests."""
    _registered_targets.clear()


def discover_targets(targets_dir: str) -> list[DiscoveredTarget]:
    """Scan the targets directory and discover all target classes.

    Walks the directory tree, imports each .py file (skipping __init__.py),
    and finds the BaseTarget subclass in each one. Each file must have exactly
    one target class.

    Args:
        targets_dir: Absolute path to the src/targets/ directory.

    Returns:
        List of discovered targets sorted by path.

    Raises:
        TargetDiscoveryError: If a file has no BaseTarget subclass, multiple
            subclasses, or fails to import.
    """
    # Check that the targets directory exists
    if not os.path.isdir(targets_dir):
        raise TargetDiscoveryError(
            f"Targets directory does not exist: {targets_dir}"
        )

    discovered: list[DiscoveredTarget] = []

    for dirpath, _dirnames, filenames in os.walk(targets_dir):
        for filename in filenames:
            # Skip __init__.py, underscore-prefixed helpers, and non-Python files
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            full_file_path: str = os.path.join(dirpath, filename)
            relative_path: str = os.path.relpath(full_file_path, targets_dir)

            # Strip .py extension and convert separators to forward slashes
            target_path: str = os.path.splitext(relative_path)[0].replace(os.sep, "/")

            # Convert path to module name for importlib
            module_path: str = "src.targets." + target_path.replace("/", ".")

            # Import the module
            try:
                spec: Any = importlib.util.spec_from_file_location(
                    module_path, full_file_path
                )
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not create module spec for {relative_path}")

                module: Any = importlib.util.module_from_spec(spec)
                # Register before exec to prevent infinite recursion on circular imports
                sys.modules[module_path] = module
                spec.loader.exec_module(module)
            except Exception as error:
                raise TargetDiscoveryError(
                    f"Failed to import target file {relative_path}: {error}"
                ) from error

            # Find BaseTarget subclasses (exclude the base classes themselves)
            base_classes: set[type] = {
                BaseTarget, IterableTarget,
                PerHostTarget, PerConfigmapTarget, PerServiceTarget,
            }
            matching_classes: list[type] = []
            for _name, cls in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(cls, BaseTarget)
                    and cls not in base_classes
                    and cls.__module__ == module_path
                ):
                    matching_classes.append(cls)

            # Must have exactly one target class per file
            if len(matching_classes) == 0:
                raise TargetDiscoveryError(
                    f"No BaseTarget subclass found in {relative_path}. "
                    f"Non-target files must be prefixed with an underscore "
                    f"(e.g. _{filename}) to be skipped during discovery."
                )

            if len(matching_classes) > 1:
                class_names: str = ", ".join(
                    cls.__name__ for cls in matching_classes
                )
                raise TargetDiscoveryError(
                    f"Multiple BaseTarget subclasses found in {relative_path}: {class_names}"
                )

            # Check if this is an iterable target (produces multiple results)
            target_class: type = matching_classes[0]
            is_per_host: bool = issubclass(target_class, IterableTarget)

            discovered.append(
                DiscoveredTarget(
                    path=target_path,
                    module_path=module_path,
                    target_class=target_class,
                    is_per_host=is_per_host,
                )
            )

    # Merge explicitly registered targets. Registered targets take precedence
    # over filesystem-discovered ones with the same path (allows overriding
    # the auto-discovered version with a decorated class).
    discovered_paths: set[str] = {dt.path for dt in discovered}
    for reg_path, reg_class in _registered_targets.items():
        if reg_path in discovered_paths:
            # Replace the filesystem-discovered target with the registered one
            discovered = [
                dt if dt.path != reg_path else DiscoveredTarget(
                    path=reg_path,
                    module_path=reg_class.__module__,
                    target_class=reg_class,
                    is_per_host=issubclass(reg_class, IterableTarget),
                )
                for dt in discovered
            ]
        else:
            # Add the registered target (not found on filesystem)
            discovered.append(DiscoveredTarget(
                path=reg_path,
                module_path=reg_class.__module__,
                target_class=reg_class,
                is_per_host=issubclass(reg_class, IterableTarget),
            ))

    # Sort by path for consistent, reproducible output
    discovered.sort(key=lambda dt: dt.path)

    return discovered


def _match_path_glob(path: str, pattern: str) -> bool:
    """Match a target path against a glob pattern with segment-aware wildcards.

    Splits both path and pattern by '/' and matches segment by segment.
    '*' matches exactly one segment (any characters within that segment).
    '**' matches zero or more segments (recursive across path boundaries).
    '?' matches any single character within a segment.

    Args:
        path: The target path to test (e.g., 'databases/cassandra/status').
        pattern: The glob pattern (e.g., 'databases/**').

    Returns:
        True if the path matches the pattern.
    """
    path_parts: list[str] = path.split("/")
    pat_parts: list[str] = pattern.split("/")

    return _match_segments(path_parts, 0, pat_parts, 0)


def _match_segments(
    path_parts: list[str],
    pi: int,
    pat_parts: list[str],
    qi: int,
) -> bool:
    """Recursively match path segments against pattern segments.

    Args:
        path_parts: Split path segments.
        pi: Current index in path_parts.
        pat_parts: Split pattern segments.
        qi: Current index in pat_parts.

    Returns:
        True if remaining path matches remaining pattern.
    """
    # Both exhausted means full match
    if pi == len(path_parts) and qi == len(pat_parts):
        return True

    # Pattern exhausted but path has segments left means no match
    if qi == len(pat_parts):
        return False

    # '**' matches zero or more segments
    if pat_parts[qi] == "**":
        # Try matching zero segments (skip the **) then one-or-more (advance path)
        if _match_segments(path_parts, pi, pat_parts, qi + 1):
            return True
        if pi < len(path_parts):
            return _match_segments(path_parts, pi + 1, pat_parts, qi)
        return False

    # Path exhausted but non-** pattern segments remain means no match
    if pi == len(path_parts):
        return False

    # Single segment: use fnmatch for * and ? within the segment
    if fnmatch.fnmatch(path_parts[pi], pat_parts[qi]):
        return _match_segments(path_parts, pi + 1, pat_parts, qi + 1)

    return False


def filter_targets(
    targets: list[DiscoveredTarget],
    pattern: str,
) -> list[DiscoveredTarget]:
    """Filter targets by a glob-like pattern.

    Supports:
    '*' or 'all' match all targets
    'databases/cassandra/cluster_status' exact match
    'databases/cassandra/*' targets directly under databases/cassandra/ (one level)
    'databases/cassandra/**' all targets under databases/cassandra/ (recursive)
    'databases/cassandra' prefix match (same as databases/cassandra/**)
    'databases' prefix match (same as databases/**)

    Uses segment-aware glob matching: '*' matches one path segment,
    '**' matches zero or more segments recursively.

    Args:
        targets: List of all discovered targets.
        pattern: The filter pattern from --target argument.

    Returns:
        Filtered list of targets matching the pattern.

    Raises:
        ValueError: If the pattern matches zero targets.
    """
    normalized: str = pattern.strip()

    # '*' or 'all' matches everything
    if normalized.lower() in ("*", "all"):
        return targets

    # Check for exact match first
    exact_matches: list[DiscoveredTarget] = [
        t for t in targets if t.path == normalized
    ]
    if exact_matches:
        return exact_matches

    # Convert bare prefixes to recursive glob patterns
    if "*" not in normalized and "?" not in normalized:
        normalized = normalized.rstrip("/")
        normalized = f"{normalized}/**"

    # Apply segment-aware glob matching
    matched: list[DiscoveredTarget] = [
        t for t in targets if _match_path_glob(t.path, normalized)
    ]

    if not matched:
        available: str = "\n".join(f"  - {t.path}" for t in targets)
        raise ValueError(
            f"No targets match pattern '{pattern}'. Available targets:\n{available}"
        )

    return matched
