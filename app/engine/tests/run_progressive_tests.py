#!/usr/bin/env python3
"""Example script for running progressive tests."""

import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.engine.tests.test_runner import RunConfig, run_progressive_tests, generate_summary_report


def main():
    """Run progressive tests with example configurations."""
    print("Progressive Test Runner Example")
    print("=" * 60)

    # Example 1: Run all levels with default settings
    print("\nExample 1: Running all test levels (0-4) with stop on failure...")
    config = RunConfig(
        start_level=0,
        end_level=4,
        stop_on_failure=True,
        verbose=False
    )
    results = run_progressive_tests(config)
    print(generate_summary_report(results))

    # Example 2: Run only unit tests (level 1) with coverage
    print("\n" + "=" * 60)
    print("\nExample 2: Running only unit tests (level 1) with coverage...")
    config = RunConfig(
        start_level=1,
        end_level=1,
        coverage=True,
        verbose=True
    )
    results = run_progressive_tests(config)

    # Example 3: Run fast tests (levels 0-1) in parallel
    print("\n" + "=" * 60)
    print("\nExample 3: Running fast tests (levels 0-1) in parallel...")
    config = RunConfig(
        start_level=0,
        end_level=1,
        parallel=True,
        stop_on_failure=False
    )
    results = run_progressive_tests(config)

    # Exit with appropriate code
    total_failed = sum(r.failed for r in results)
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())