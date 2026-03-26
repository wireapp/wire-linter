"""Auto-discovery for test functions in the Wire Fact Gathering Tool.

Replaces the old hand-maintained import block and ALL_TESTS list. Test modules
follow test_NNN_*_unit.py naming, test functions start with test_.

Discovery:
  1. Scan src/test/ for test_*_unit.py files.
  2. Sort by numeric prefix (NNN) for stable execution order.
  3. Import each module dynamically via importlib.
  4. Collect callables starting with test_ that are actually defined here
     (not just imported), preserving source order (Python 3.7+ dict ordering).

Just add new test files/functions discovery picks them up automatically.
Zero maintenance.

Used by:
  Imported by src/test/test_registry.py, which re-exports ALL_TESTS.
  No hard dependency on specific modules; discovers at import time.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from collections.abc import Callable

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

# Add project root to sys.path so 'src.test.test_NNN_*' module names resolve
# correctly regardless of where Python is invoked from.
_project_root: str = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

# Pattern for test_NNN_<name>_unit.py files, captures the NNN part.
_UNIT_FILE_PATTERN: re.Pattern[str] = re.compile(
    r'^test_(\d+)_.*_unit\.py$'
)


def _discover_test_files(test_dir: str) -> list[tuple[int, str]]:
    """Return (numeric_prefix, filename) pairs for unit test files.

    Only matches test_NNN_*_unit.py; ignores everything else.

    Args:
        test_dir: Absolute path to scan.

    Returns:
        List of (numeric_prefix, filename) tuples, sorted by prefix.
    """
    entries: list[tuple[int, str]] = []
    for filename in os.listdir(test_dir):
        match = _UNIT_FILE_PATTERN.match(filename)
        if match:
            # Group 1 is the numeric prefix (e.g. "000", "007", "020").
            entries.append((int(match.group(1)), filename))

    # Sort ascending so modules (and tests) run in the same order every time.
    entries.sort(key=lambda pair: pair[0])
    return entries


def _collect_tests_from_module(module: object, module_name: str) -> list[Callable[[], None]]:
    """Return test callables defined in this module, in definition order.

    Uses module.__dict__ (insertion-ordered since Python 3.7) to preserve source order.
    The __module__ guard filters out imported names.

    Args:
        module:      Imported module object.
        module_name: Fully-qualified module name (e.g. 'src.test.test_000_…').

    Returns:
        List of zero-argument callables starting with 'test_'.
    """
    tests: list[Callable[[], None]] = []
    for name, obj in vars(module).items():
        # Only accept test_ prefixed callables that actually live in this module,
        # not ones just imported from elsewhere.
        if (
            name.startswith('test_')
            and callable(obj)
            and getattr(obj, '__module__', None) == module_name
        ):
            tests.append(obj)
    return tests


def discover_all_tests() -> list[Callable[[], None]]:
    """Discover and return all test functions from unit test modules.

    Scans the directory containing this file, imports test_NNN_*_unit.py files
    in numeric order, and collects their test_ functions.

    Returns:
        Ordered list of zero-argument test callables ready to run.
    """
    # This file lives in src/test/, so its directory is the test directory.
    test_dir: str = os.path.dirname(os.path.abspath(__file__))

    all_tests: list[Callable[[], None]] = []

    for _prefix, filename in _discover_test_files(test_dir):
        # Strip the .py suffix for the bare module name, then add the package
        # path to match how the project's imports work.
        module_basename: str = filename[:-3]
        module_name: str = f'src.test.{module_basename}'

        module = importlib.import_module(module_name)
        all_tests.extend(_collect_tests_from_module(module, module_name))

    return all_tests


# ---------------------------------------------------------------------------
# Module-level constant evaluated once at import time.
# ---------------------------------------------------------------------------

# Build the test list right away so any import errors in test modules surface
# at startup instead of when the first test runs.
ALL_TESTS: list[Callable[[], None]] = discover_all_tests()
