"""Tests for target discovery and filtering (src/lib/target_discovery.py)."""

import os
import unittest

from src.lib.target_discovery import DiscoveredTarget, discover_targets, filter_targets


def mock_target(path: str) -> DiscoveredTarget:
    """Create a mock DiscoveredTarget with dummy values.

    Nice for filter tests so we don't have to mess with the file system
    or import machinery.

    Args:
        path: The target path (e.g., «host/disk_usage»).

    Returns:
        A DiscoveredTarget with placeholder module_path, target_class, is_per_host.
    """
    return DiscoveredTarget(
        path=path,
        module_path=f"src.targets.{path.replace('/', '.')}",
        target_class=type("MockTarget", (), {}),
        is_per_host=False,
    )


class TestDiscoverTargets(unittest.TestCase):
    """Test discover_targets against the real filesystem."""

    def _get_targets_dir(self) -> str:
        """Get absolute path to src/targets/."""
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "targets")
        )

    def test_discover_finds_all_targets(self) -> None:
        """Find all target files under src/targets/."""
        targets_dir = self._get_targets_dir()
        targets = discover_targets(targets_dir)

        # We expect at least 40 targets across all categories
        self.assertGreaterEqual(len(targets), 40)

        # Spot-check some known targets exist
        paths = [t.path for t in targets]
        self.assertIn("host/disk_usage", paths)
        self.assertIn("databases/cassandra/cluster_status", paths)

    def test_discover_targets_sorted(self) -> None:
        """Discovered targets are sorted alphabetically by path."""
        targets_dir = self._get_targets_dir()
        targets = discover_targets(targets_dir)

        paths = [t.path for t in targets]
        self.assertEqual(paths, sorted(paths))

    def test_discover_skips_init_files(self) -> None:
        """Skip __init__.py files."""
        targets_dir = self._get_targets_dir()
        targets = discover_targets(targets_dir)

        self.assertTrue(
            all("__init__" not in t.path for t in targets)
        )


class TestFilterTargets(unittest.TestCase):
    """Test filter_targets with mock targets."""

    def test_filter_exact_match(self) -> None:
        """Exact path match returns only that target."""
        targets = [
            mock_target("host/disk_usage"),
            mock_target("host/memory_usage"),
        ]
        filtered = filter_targets(targets, "host/disk_usage")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].path, "host/disk_usage")

    def test_filter_prefix_match(self) -> None:
        """Prefix match returns all targets under that prefix."""
        targets = [
            mock_target("databases/cassandra/cluster_status"),
            mock_target("databases/elasticsearch/cluster_health"),
            mock_target("host/disk_usage"),
        ]
        filtered = filter_targets(targets, "databases")

        self.assertEqual(len(filtered), 2)
        self.assertTrue(
            all(t.path.startswith("databases/") for t in filtered)
        )

    def test_filter_glob(self) -> None:
        """Glob patterns with wildcards work."""
        targets = [
            mock_target("databases/cassandra/cluster_status"),
            mock_target("databases/cassandra/node_count"),
            mock_target("databases/elasticsearch/cluster_health"),
        ]
        filtered = filter_targets(targets, "databases/cassandra/*")

        self.assertEqual(len(filtered), 2)
        self.assertTrue(
            all(t.path.startswith("databases/cassandra/") for t in filtered)
        )

    def test_filter_all_star(self) -> None:
        """Wildcard '*' matches everything."""
        targets = [mock_target("a/b"), mock_target("c/d")]
        filtered = filter_targets(targets, "*")

        self.assertEqual(len(filtered), 2)

    def test_filter_all_keyword(self) -> None:
        """Keyword 'all' matches everything."""
        targets = [mock_target("a/b"), mock_target("c/d")]
        filtered = filter_targets(targets, "all")

        self.assertEqual(len(filtered), 2)

    def test_filter_no_match_raises_valueerror(self) -> None:
        """Raise ValueError when pattern matches nothing."""
        targets = [
            mock_target("host/disk_usage"),
            mock_target("host/memory_usage"),
        ]
        with self.assertRaises(ValueError):
            filter_targets(targets, "nonexistent/target")

    def test_filter_nested_prefix(self) -> None:
        """Mid-level prefix matches all targets under it (deeply nested too)."""
        targets = [
            mock_target("databases/cassandra/cluster_status"),
            mock_target("databases/cassandra/node_count"),
            mock_target("databases/elasticsearch/health"),
        ]
        filtered = filter_targets(targets, "databases/cassandra")

        self.assertEqual(len(filtered), 2)


if __name__ == '__main__':
    unittest.main()
