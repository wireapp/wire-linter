"""Test runner entry point for the Wire Fact Gathering Tool.

Thin glue: imports the ordered test list from the registry and hands it
to the runner engine.

  test_registry.py imports the test functions in order
  test_runner_engine.py handles execution, tracking, and reporting
  this file wires them together
"""

from __future__ import annotations

import os
import sys

# Add project root to sys.path for direct execution
_project_root: str = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Full ordered list of tests to run
from src.test.test_registry import ALL_TESTS

# Execution engine with tracking and reporting
from src.test.test_runner_engine import run_tests


if __name__ == '__main__':
    run_tests(ALL_TESTS)
