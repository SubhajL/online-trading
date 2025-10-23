from typing import Any

#!/usr/bin/env python3
"""
Fix all connection type annotation errors by running mypy and automatically fixing them
"""

import re
import subprocess

from connection_fixer import fix_file_connection_annotations


def get_files_with_connection_errors() -> Any:
    """Run mypy and extract files with connection annotation errors"""
    result = subprocess.run(
        ["python", "-m", "mypy", "app/engine"],
        check=False, capture_output=True,
        text=True,
    )

    files_to_fix = set()

    # Look for get_connection patterns with incorrect return types
    for line in result.stdout.split("\n"):
        if "-> None:" in line and "get_connection" in line:
            match = re.match(r"(app/engine/[^:]+):", line)
            if match:
                files_to_fix.add(match.group(1))

    # Look for var-annotated errors related to connections
    for line in result.stdout.split("\n"):
        if "var-annotated" in line and any(keyword in line for keyword in ["connection", "conn", "pool"]):
            match = re.match(r"(app/engine/[^:]+):", line)
            if match:
                files_to_fix.add(match.group(1))

    return sorted(files_to_fix)


def fix_all_connection_annotations() -> None:
    """Fix connection annotations in all files that need it"""
    files = get_files_with_connection_errors()

    if not files:
        print("No connection annotation errors found!")
        return

    print(f"Found {len(files)} files with connection annotation issues:")
    for file_path in files:
        print(f"  - {file_path}")

    print("\nFixing connection annotations...")
    fixed_count = 0

    for file_path in files:
        if fix_file_connection_annotations(file_path):
            print(f"✓ Fixed {file_path}")
            fixed_count += 1
        else:
            print(f"✗ No changes needed in {file_path}")

    print(f"\nFixed {fixed_count} files")

    # Run mypy again to verify
    print("\nVerifying fixes...")
    result = subprocess.run(
        ["python", "-m", "mypy", "app/engine", "--no-error-summary"],
        check=False, capture_output=True,
        text=True,
    )

    # Count remaining connection-related errors
    remaining_errors = 0
    for line in result.stdout.split("\n"):
        if ("var-annotated" in line and any(keyword in line for keyword in ["connection", "conn", "pool"])) or ("-> None:" in line and "get_connection" in line):
            remaining_errors += 1

    print(f"Remaining connection annotation errors: {remaining_errors}")


if __name__ == "__main__":
    fix_all_connection_annotations()
