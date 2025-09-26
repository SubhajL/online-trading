"""Progressive test runner that executes tests by level."""

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from app.engine.tests.level_mapping import categorize_existing_tests, generate_level_report


@dataclass
class LevelResult:
    """Results from running tests at a specific level."""

    level: int
    passed: int
    failed: int
    skipped: int
    duration: float
    output: str
    test_files: List[str]


@dataclass
class RunConfig:
    """Configuration for test run."""

    start_level: int = 0
    end_level: int = 4
    stop_on_failure: bool = True
    verbose: bool = False
    parallel: bool = False
    coverage: bool = False
    pytest_args: List[str] = None


def run_tests_at_level(level: int, test_files: List[str], config: RunConfig) -> LevelResult:
    """
    Run all tests at a specific level.

    Args:
        level: Test level (0-4)
        test_files: List of test file paths
        config: Run configuration

    Returns:
        Result of test execution
    """
    if not test_files:
        return LevelResult(
            level=level,
            passed=0,
            failed=0,
            skipped=0,
            duration=0.0,
            output="No tests at this level",
            test_files=[]
        )

    start_time = time.time()

    # Build pytest command
    cmd = ["python", "-m", "pytest"]

    # Add test files
    cmd.extend(test_files)

    # Add standard args
    cmd.extend([
        "-v" if config.verbose else "-q",
        "--tb=short",
        "--no-header",
    ])

    # Add parallel execution if enabled
    if config.parallel and len(test_files) > 1:
        cmd.extend(["-n", "auto"])

    # Add coverage if enabled
    if config.coverage:
        cmd.extend([
            "--cov=app.engine",
            "--cov-report=term-missing",
            f"--cov-report=html:coverage/level_{level}",
        ])

    # Add any custom pytest args
    if config.pytest_args:
        cmd.extend(config.pytest_args)

    # Run tests
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent  # Project root
        )

        output = result.stdout + "\n" + result.stderr

        # Parse pytest output for counts
        passed, failed, skipped = parse_pytest_output(output)

        duration = time.time() - start_time

        return LevelResult(
            level=level,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration=duration,
            output=output,
            test_files=test_files
        )

    except Exception as e:
        duration = time.time() - start_time
        return LevelResult(
            level=level,
            passed=0,
            failed=len(test_files),
            skipped=0,
            duration=duration,
            output=f"Error running tests: {str(e)}",
            test_files=test_files
        )


def parse_pytest_output(output: str) -> Tuple[int, int, int]:
    """
    Parse pytest output to extract test counts.

    Args:
        output: Raw pytest output

    Returns:
        Tuple of (passed, failed, skipped)
    """
    passed = failed = skipped = 0

    # Look for pytest summary line
    for line in output.split('\n'):
        if ' passed' in line or ' failed' in line or ' skipped' in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if 'passed' in part and i > 0:
                    try:
                        passed = int(parts[i-1])
                    except ValueError:
                        pass
                elif 'failed' in part and i > 0:
                    try:
                        failed = int(parts[i-1])
                    except ValueError:
                        pass
                elif 'skipped' in part and i > 0:
                    try:
                        skipped = int(parts[i-1])
                    except ValueError:
                        pass

    return passed, failed, skipped


def run_progressive_tests(config: RunConfig = None) -> List[LevelResult]:
    """
    Run tests progressively from lower to higher levels.

    Args:
        config: Test run configuration

    Returns:
        Results for each level
    """
    if config is None:
        config = RunConfig()

    # Categorize tests by level
    categorized = categorize_existing_tests()

    results = []

    for level in range(config.start_level, config.end_level + 1):
        test_files = categorized.get(level, [])

        print(f"\n{'=' * 60}")
        print(f"Running Level {level} Tests")
        print(f"{'=' * 60}")

        if not test_files:
            print("No tests at this level")
            continue

        print(f"Found {len(test_files)} test files:")
        for tf in test_files[:3]:  # Show first 3
            print(f"  - {tf}")
        if len(test_files) > 3:
            print(f"  ... and {len(test_files) - 3} more")

        # Run tests at this level
        result = run_tests_at_level(level, test_files, config)
        results.append(result)

        # Show summary
        print(f"\nLevel {level} Summary:")
        print(f"  Passed: {result.passed}")
        print(f"  Failed: {result.failed}")
        print(f"  Skipped: {result.skipped}")
        print(f"  Duration: {result.duration:.2f}s")

        # Stop on failure if configured
        if config.stop_on_failure and result.failed > 0:
            print(f"\n❌ Stopping due to failures at level {level}")
            break

    return results


def generate_summary_report(results: List[LevelResult]) -> str:
    """
    Generate a summary report of all test levels.

    Args:
        results: Results from each level

    Returns:
        Formatted summary report
    """
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("PROGRESSIVE TEST SUMMARY")
    lines.append("=" * 60)

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_skipped = sum(r.skipped for r in results)
    total_duration = sum(r.duration for r in results)

    lines.append(f"\nOverall Results:")
    lines.append(f"  Total Passed: {total_passed}")
    lines.append(f"  Total Failed: {total_failed}")
    lines.append(f"  Total Skipped: {total_skipped}")
    lines.append(f"  Total Duration: {total_duration:.2f}s")

    lines.append(f"\nBy Level:")
    level_names = {
        0: "Import tests",
        1: "Unit tests",
        2: "Service tests",
        3: "Integration tests",
        4: "End-to-end tests"
    }

    for result in results:
        status = "✅" if result.failed == 0 else "❌"
        lines.append(f"\n  Level {result.level} ({level_names.get(result.level, 'Unknown')}):")
        lines.append(f"    Status: {status}")
        lines.append(f"    Tests: {result.passed + result.failed + result.skipped}")
        lines.append(f"    Passed: {result.passed}")
        lines.append(f"    Failed: {result.failed}")
        lines.append(f"    Duration: {result.duration:.2f}s")

    # Add recommendations
    if total_failed > 0:
        lines.append(f"\n{'=' * 60}")
        lines.append("RECOMMENDATIONS:")
        lines.append("=" * 60)

        for result in results:
            if result.failed > 0:
                lines.append(f"\nLevel {result.level} had {result.failed} failures:")
                lines.append(f"  Run with --verbose to see detailed output:")
                lines.append(f"  python -m app.engine.tests.test_runner --level {result.level} --verbose")

    lines.append("")
    return "\n".join(lines)


def main():
    """Command line interface for test runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run tests progressively by level",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Levels:
  0 - Import tests (no dependencies)
  1 - Unit tests (mocked dependencies)
  2 - Service tests (real DB/Redis)
  3 - Integration tests (all services)
  4 - End-to-end tests (with UI)

Examples:
  # Run all levels
  python -m app.engine.tests.test_runner

  # Run only unit tests
  python -m app.engine.tests.test_runner --level 1

  # Run levels 0-2 with coverage
  python -m app.engine.tests.test_runner --start 0 --end 2 --coverage

  # Continue on failure
  python -m app.engine.tests.test_runner --no-stop-on-failure
        """
    )

    parser.add_argument(
        "--level",
        type=int,
        help="Run only a specific level (0-4)"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Starting level (default: 0)"
    )
    parser.add_argument(
        "--end",
        type=int,
        default=4,
        help="Ending level (default: 4)"
    )
    parser.add_argument(
        "--no-stop-on-failure",
        action="store_true",
        help="Continue running even if tests fail"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--parallel", "-n",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Generate coverage reports"
    )
    parser.add_argument(
        "--show-distribution",
        action="store_true",
        help="Show test distribution by level and exit"
    )

    args = parser.parse_args()

    # Show distribution if requested
    if args.show_distribution:
        print(generate_level_report())
        return 0

    # Build config
    config = RunConfig(
        stop_on_failure=not args.no_stop_on_failure,
        verbose=args.verbose,
        parallel=args.parallel,
        coverage=args.coverage
    )

    # Handle single level
    if args.level is not None:
        config.start_level = args.level
        config.end_level = args.level
    else:
        config.start_level = args.start
        config.end_level = args.end

    # Run tests
    results = run_progressive_tests(config)

    # Show summary
    print(generate_summary_report(results))

    # Exit code based on failures
    total_failed = sum(r.failed for r in results)
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())