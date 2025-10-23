#!/usr/bin/env python3
"""Example of running preflight checks."""

from app.engine.preflight.run_checks import generate_preflight_report, run_all_checks


def main():
    """Run preflight checks and display results."""
    print("Running preflight checks...")

    # Run all checks
    results = run_all_checks()

    # Generate and print report
    report = generate_preflight_report(results)
    print(report)

    # Exit with appropriate code
    if results.can_proceed:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()
