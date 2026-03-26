"""Generic test runner engine for the Wire Fact Gathering Tool.

Does one job: take a list of callables, run each one, count passes/fails, print
tracebacks on breaks, exit with the right code.

Pulled out of run_tests.py so you can run subsets, integrate with CI, or do
parallel runs without modifying this file.

Connections:
  Called by src/test/run_tests.py
  Doesn't care about test_registry.py or specific modules, just needs
    each item to be callable
"""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable

from src.test.conftest import reset_test_caches


def run_tests(tests: list[Callable[[], None]]) -> None:
    """Run each callable and print results.

    Args:
        tests: List of zero-argument callables (raise on failure,
               return normally on success).

    Returns:
        None (exits 0 on success, 1 on failure)
    """
    # Start counting
    passed: int = 0
    failed: int = 0

    # Grab the total now (before running) so the summary denominator doesn't
    # change if someone messes with the list during execution
    total: int = len(tests)

    for test_fn in tests:
        # Just use the function name, keep it simple
        name: str = test_fn.__name__
        try:
            # Clear module-level caches before each test so stale data
            # from one test cannot leak into the next
            reset_test_caches()
            test_fn()
            passed += 1
            print(f"  PASSED  {name}")
        except Exception as e:
            failed += 1
            print(f"  FAILED  {name}: {e}")

            # Show the full traceback so you can see which line actually broke
            traceback.print_exc()

    # Print the fraction first so you see the ratio at a glance
    print(f"\n{passed}/{total} tests passed")
    if failed > 0:
        print(f"{failed} test(s) FAILED")

        # Tell the shell/CI this failed
        sys.exit(1)
    else:
        print("All tests passed!")

        # Exit cleanly
        sys.exit(0)
