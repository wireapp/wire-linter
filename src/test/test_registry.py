"""Test registry for the Wire Fact Gathering Tool.

A re-export shim the real work is in test_discovery_auto, which scans src/test/
for unit test files and builds ALL_TESTS automatically.

Kept for backwards compatibility. CI filters, coverage scripts, and other tooling
import ALL_TESTS from here.

Connections:
  run_tests.py imports ALL_TESTS to execute tests
  test_discovery_auto.py does the actual discovery work
"""

from __future__ import annotations

# Re-export ALL_TESTS from auto-discovery so existing consumers
# (run_tests.py, CI scripts) don't need any import changes
from src.test.test_discovery_auto import ALL_TESTS

__all__ = ['ALL_TESTS']
