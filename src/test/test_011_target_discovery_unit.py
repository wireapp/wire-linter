"""Unit tests for the target_discovery module.

Tests directory scanning, importing, finding classes, paths, PerHostTarget stuff,
errors, pattern matching with filter_targets, and all the edge cases.
"""

from __future__ import annotations

# External
import os
import tempfile

# Ours
from src.lib.target_discovery import (
    TargetDiscoveryError,
    DiscoveredTarget,
    discover_targets,
    filter_targets,
    register_target,
    get_registered_targets,
    clear_registered_targets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_target_file(
    targets_dir: str,
    relative_path: str,
    content: str,
) -> str:
    """Write a Python file at the given relative path under targets_dir.

    Creates any missing parent directories so you don't have to set them up yourself.

    Args:
        targets_dir: The root targets directory.
        relative_path: File path relative to targets_dir (e.g., «db/status.py»).
        content: Python source code to write.

    Returns:
        Absolute path to the created file.
    """
    full_path: str = os.path.join(targets_dir, relative_path)

    # Make sure all parent directories exist so nested files don't break.
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    return full_path


# A real target that inherits from BaseTarget.
SIMPLE_TARGET_CODE: str = """
from src.lib.base_target import BaseTarget

class SimpleTarget(BaseTarget):
    @property
    def description(self) -> str:
        return "Simple target"

    def collect(self):
        return 42
"""

# A real target that inherits from PerHostTarget.
PER_HOST_TARGET_CODE: str = """
from src.lib.per_host_target import PerHostTarget

class DiskTarget(PerHostTarget):
    @property
    def description(self) -> str:
        return "Disk usage"

    def get_hosts(self):
        return []

    def collect_for_host(self, host):
        return 0
"""

# File with no BaseTarget subclass... should error out.
NO_TARGET_CODE: str = """
class SomethingElse:
    pass
"""

# File with multiple BaseTarget subclasses... ambiguous and should blow up.
MULTI_TARGET_CODE: str = """
from src.lib.base_target import BaseTarget

class TargetA(BaseTarget):
    @property
    def description(self) -> str:
        return "A"
    def collect(self):
        return "a"

class TargetB(BaseTarget):
    @property
    def description(self) -> str:
        return "B"
    def collect(self):
        return "b"
"""

# File with a syntax error... should fail during import.
SYNTAX_ERROR_CODE: str = """
def broken(
    # missing closing paren
"""


# ---------------------------------------------------------------------------
# TargetDiscoveryError
# ---------------------------------------------------------------------------

def test_target_discovery_error_is_exception() -> None:
    """Check that TargetDiscoveryError is actually an Exception.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    err: TargetDiscoveryError = TargetDiscoveryError("test message")

    # Should be catchable as a regular Exception.
    assert isinstance(err, Exception)
    assert str(err) == "test message"


# ---------------------------------------------------------------------------
# DiscoveredTarget dataclass
# ---------------------------------------------------------------------------

def test_discovered_target_fields() -> None:
    """Check that DiscoveredTarget has all its fields.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    dt: DiscoveredTarget = DiscoveredTarget(
        path="databases/cassandra/status",
        module_path="src.targets.databases.cassandra.status",
        target_class=type,
        is_per_host=False,
    )

    assert dt.path == "databases/cassandra/status"
    assert dt.module_path == "src.targets.databases.cassandra.status"

    # is_per_host should be False by default for normal BaseTarget subclasses.
    assert dt.is_per_host is False


# ---------------------------------------------------------------------------
# discover_targets non-existent directory
# ---------------------------------------------------------------------------

def test_discover_targets_nonexistent_directory() -> None:
    """Check that discover_targets errors when the directory doesn't exist.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    try:
        # Use a path that definitely won't exist.
        discover_targets("/tmp/__nonexistent_targets_dir_xyz__")
        assert False, "Should have raised TargetDiscoveryError"
    except TargetDiscoveryError as err:
        # Error message should be clear about what went wrong.
        assert "does not exist" in str(err)


# ---------------------------------------------------------------------------
# discover_targets empty directory
# ---------------------------------------------------------------------------

def test_discover_targets_empty_directory() -> None:
    """Check that discover_targets returns nothing for an empty directory.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        # Empty dir, no targets found.
        assert result == []


# ---------------------------------------------------------------------------
# discover_targets single target
# ---------------------------------------------------------------------------

def test_discover_targets_single_file() -> None:
    """Check that discover_targets finds a single target file.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "status.py", SIMPLE_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        assert len(result) == 1

        # Path is just the file stem, relative to targets dir.
        assert result[0].path == "status"
        assert result[0].is_per_host is False
        assert result[0].target_class.__name__ == "SimpleTarget"


# ---------------------------------------------------------------------------
# discover_targets nested directory structure
# ---------------------------------------------------------------------------

def test_discover_targets_nested() -> None:
    """Check that discover_targets handles nested directory structures.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "databases/cassandra/status.py", SIMPLE_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        assert len(result) == 1

        # Nested paths use forward slashes, regardless of OS.
        assert result[0].path == "databases/cassandra/status"


# ---------------------------------------------------------------------------
# discover_targets multiple targets sorted
# ---------------------------------------------------------------------------

def test_discover_targets_multiple_sorted() -> None:
    """Check that discover_targets returns targets sorted by path.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write them backwards to make sure sorting actually happens.
        _write_target_file(tmpdir, "z_target.py", SIMPLE_TARGET_CODE)
        _write_target_file(tmpdir, "a_target.py", SIMPLE_TARGET_CODE)
        _write_target_file(tmpdir, "m/nested.py", SIMPLE_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        paths: list[str] = [t.path for t in result]

        # Sorting keeps output consistent and makes filtering predictable.
        assert paths == sorted(paths), f"Targets should be sorted: {paths}"


# ---------------------------------------------------------------------------
# discover_targets PerHostTarget detection
# ---------------------------------------------------------------------------

def test_discover_targets_per_host() -> None:
    """Check that discover_targets spots PerHostTarget subclasses.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "vm/disk.py", PER_HOST_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        assert len(result) == 1

        # is_per_host should be True so the runner knows to use execute_all instead of execute.
        assert result[0].is_per_host is True
        assert result[0].path == "vm/disk"


# ---------------------------------------------------------------------------
# discover_targets skips __init__.py
# ---------------------------------------------------------------------------

def test_discover_targets_skips_init() -> None:
    """Check that discover_targets skips __init__.py files.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # __init__.py is just a package marker, not a target.
        _write_target_file(tmpdir, "__init__.py", "# package init")
        _write_target_file(tmpdir, "status.py", SIMPLE_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        assert len(result) == 1
        assert result[0].path == "status"


# ---------------------------------------------------------------------------
# discover_targets skips non-Python files
# ---------------------------------------------------------------------------

def test_discover_targets_skips_non_python() -> None:
    """Check that discover_targets ignores non-.py files.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Skip markdown and JSON... only .py files count as targets.
        _write_target_file(tmpdir, "readme.md", "# Targets")
        _write_target_file(tmpdir, "data.json", '{"key": "value"}')
        _write_target_file(tmpdir, "status.py", SIMPLE_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        assert len(result) == 1


# ---------------------------------------------------------------------------
# discover_targets error: no BaseTarget subclass
# ---------------------------------------------------------------------------

def test_discover_targets_no_target_class() -> None:
    """Check that discover_targets errors if a file doesn't have a BaseTarget subclass.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "not_a_target.py", NO_TARGET_CODE)

        try:
            discover_targets(tmpdir)
            assert False, "Should have raised TargetDiscoveryError"
        except TargetDiscoveryError as err:
            # Error message should clearly say what's wrong.
            assert "No BaseTarget subclass" in str(err)


# ---------------------------------------------------------------------------
# discover_targets error: multiple BaseTarget subclasses
# ---------------------------------------------------------------------------

def test_discover_targets_multiple_classes() -> None:
    """Check that discover_targets errors if a file has multiple BaseTarget subclasses.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "multi.py", MULTI_TARGET_CODE)

        try:
            discover_targets(tmpdir)
            assert False, "Should have raised TargetDiscoveryError"
        except TargetDiscoveryError as err:
            # A file should have exactly one target class, not more.
            assert "Multiple BaseTarget subclasses" in str(err)


# ---------------------------------------------------------------------------
# discover_targets error: import failure
# ---------------------------------------------------------------------------

def test_discover_targets_syntax_error() -> None:
    """Check that discover_targets errors on files with syntax errors.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "broken.py", SYNTAX_ERROR_CODE)

        try:
            discover_targets(tmpdir)
            assert False, "Should have raised TargetDiscoveryError"
        except TargetDiscoveryError as err:
            # Import errors should be wrapped in a helpful message.
            assert "Failed to import" in str(err)


# ---------------------------------------------------------------------------
# discover_targets module_path construction
# ---------------------------------------------------------------------------

def test_discover_targets_module_path() -> None:
    """Check that module_path is built correctly from the file location.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_target_file(tmpdir, "databases/pg/connections.py", SIMPLE_TARGET_CODE)

        result: list[DiscoveredTarget] = discover_targets(tmpdir)

        # module_path uses dots and is rooted at src.targets.
        assert result[0].module_path == "src.targets.databases.pg.connections"


# ---------------------------------------------------------------------------
# filter_targets wildcard patterns
# ---------------------------------------------------------------------------

def _make_sample_targets() -> list[DiscoveredTarget]:
    """Build sample DiscoveredTarget objects for testing the filter.

    Args:
        (none)

    Returns:
        Five DiscoveredTarget instances across different domains.
    """
    return [
        DiscoveredTarget(
            path="databases/cassandra/status",
            module_path="src.targets.databases.cassandra.status",
            target_class=type, is_per_host=False,
        ),
        DiscoveredTarget(
            path="databases/cassandra/connections",
            module_path="src.targets.databases.cassandra.connections",
            target_class=type, is_per_host=False,
        ),
        DiscoveredTarget(
            path="databases/elasticsearch/health",
            module_path="src.targets.databases.elasticsearch.health",
            target_class=type, is_per_host=False,
        ),
        DiscoveredTarget(
            path="kubernetes/nodes",
            module_path="src.targets.kubernetes.nodes",
            target_class=type, is_per_host=False,
        ),
        DiscoveredTarget(
            path="vm/disk_usage",
            module_path="src.targets.vm.disk_usage",
            target_class=type, is_per_host=True,
        ),
    ]


def test_filter_targets_star() -> None:
    """Check that '*' matches everything.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    result: list[DiscoveredTarget] = filter_targets(targets, "*")

    # Star gets you all targets, no filtering.
    assert len(result) == 5


def test_filter_targets_all() -> None:
    """Check that 'all' matches all targets (case-insensitive).

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    # 'ALL' in caps should work the same as '*'.
    result: list[DiscoveredTarget] = filter_targets(targets, "ALL")

    assert len(result) == 5


# ---------------------------------------------------------------------------
# filter_targets exact match
# ---------------------------------------------------------------------------

def test_filter_targets_exact_match() -> None:
    """Check that exact path matches work.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    result: list[DiscoveredTarget] = filter_targets(targets, "kubernetes/nodes")

    assert len(result) == 1
    assert result[0].path == "kubernetes/nodes"


# ---------------------------------------------------------------------------
# filter_targets prefix matching
# ---------------------------------------------------------------------------

def test_filter_targets_prefix() -> None:
    """Check that prefix without glob expands to prefix/**.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    result: list[DiscoveredTarget] = filter_targets(targets, "databases/cassandra")

    # Both cassandra targets match when you use the prefix.
    assert len(result) == 2
    paths: list[str] = [t.path for t in result]
    assert "databases/cassandra/status" in paths
    assert "databases/cassandra/connections" in paths


def test_filter_targets_top_level_prefix() -> None:
    """Check that top-level prefix matches all nested targets.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    result: list[DiscoveredTarget] = filter_targets(targets, "databases")

    # Three database targets match, but not kubernetes or vm.
    assert len(result) == 3


# ---------------------------------------------------------------------------
# filter_targets glob patterns
# ---------------------------------------------------------------------------

def test_filter_targets_glob_star() -> None:
    """Check that single * glob matches one level.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    result: list[DiscoveredTarget] = filter_targets(targets, "databases/cassandra/*")

    # Single star matches the two cassandra targets.
    assert len(result) == 2


def test_filter_targets_glob_double_star() -> None:
    """Check that ** glob matches across multiple levels.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    result: list[DiscoveredTarget] = filter_targets(targets, "databases/**")

    # Double star goes through directory boundaries and gets all three database targets.
    assert len(result) == 3


# ---------------------------------------------------------------------------
# filter_targets no match
# ---------------------------------------------------------------------------

def test_filter_targets_no_match() -> None:
    """Check that filter_targets raises ValueError when nothing matches.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    try:
        filter_targets(targets, "nonexistent/path")
        assert False, "Should have raised ValueError"
    except ValueError as err:
        # Error should say what didn't work and show what's available.
        assert "No targets match" in str(err)
        assert "databases/cassandra/status" in str(err)


# ---------------------------------------------------------------------------
# filter_targets trailing slash stripped
# ---------------------------------------------------------------------------

def test_filter_targets_trailing_slash() -> None:
    """Check that trailing slashes are stripped before matching.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    # Trailing slash is a common typo... strip it and keep matching working.
    result: list[DiscoveredTarget] = filter_targets(targets, "databases/cassandra/")

    assert len(result) == 2


# ---------------------------------------------------------------------------
# filter_targets whitespace trimmed
# ---------------------------------------------------------------------------

def test_filter_targets_whitespace() -> None:
    """Check that leading and trailing whitespace is trimmed.

    Args:
        (none)

    Returns:
        None, or AssertionError if something's wrong.
    """
    targets: list[DiscoveredTarget] = _make_sample_targets()

    # Whitespace around CLI args is a common copy-paste thing... just trim it.
    result: list[DiscoveredTarget] = filter_targets(targets, "  kubernetes/nodes  ")

    assert len(result) == 1
    assert result[0].path == "kubernetes/nodes"


# ===========================================================================
# register_target decorator
# ===========================================================================

def test_register_target_adds_to_registry() -> None:
    """@register_target adds the class to the global registry."""
    clear_registered_targets()

    from src.lib.base_target import BaseTarget

    @register_target("test/registered")
    class _Registered(BaseTarget):
        @property
        def description(self) -> str:
            return "registered"

        def collect(self) -> str:
            return "ok"

    registry: dict = get_registered_targets()
    assert "test/registered" in registry
    assert registry["test/registered"] is _Registered

    # Cleanup so other tests aren't affected
    clear_registered_targets()


def test_register_target_duplicate_path_raises() -> None:
    """@register_target raises on duplicate path."""
    clear_registered_targets()

    from src.lib.base_target import BaseTarget

    @register_target("test/dup")
    class _First(BaseTarget):
        @property
        def description(self) -> str:
            return "first"

        def collect(self) -> str:
            return "ok"

    try:
        @register_target("test/dup")
        class _Second(BaseTarget):
            @property
            def description(self) -> str:
                return "second"

            def collect(self) -> str:
                return "ok"

        assert False, "Should have raised TargetDiscoveryError"
    except TargetDiscoveryError as e:
        assert "Duplicate" in str(e)
    finally:
        clear_registered_targets()


def test_clear_registered_targets() -> None:
    """clear_registered_targets empties the registry."""
    clear_registered_targets()

    from src.lib.base_target import BaseTarget

    @register_target("test/clear")
    class _Tmp(BaseTarget):
        @property
        def description(self) -> str:
            return "tmp"

        def collect(self) -> str:
            return "ok"

    assert len(get_registered_targets()) == 1
    clear_registered_targets()
    assert len(get_registered_targets()) == 0
