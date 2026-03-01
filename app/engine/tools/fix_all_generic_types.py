#!/usr/bin/env python3
"""
Script to fix all generic type parameter errors by running mypy and applying fixes
"""

import os
from pathlib import Path
import re
import subprocess

from generic_type_fixer import fix_file_generic_types


def extract_generic_type_errors(mypy_output: str) -> list[str]:
    """Extract files with generic type errors from mypy output"""
    files = set()

    # Pattern for generic type errors - missing type parameters
    patterns = [
        r"(.+\.py):\d+: error: Missing type parameters for generic type",
        r'(.+\.py):\d+: error: "dict" expects \d+ type argument',
        r'(.+\.py):\d+: error: "list" expects \d+ type argument',
        r'(.+\.py):\d+: error: "tuple" expects at least \d+ type argument',
        r'(.+\.py):\d+: error: "Dict" expects \d+ type argument',
        r'(.+\.py):\d+: error: "List" expects \d+ type argument',
        r'(.+\.py):\d+: error: "Tuple" expects at least \d+ type argument',
        r'(.+\.py):\d+: error: "Callable" expects \d+ type argument',
        r'(.+\.py):\d+: error: "Task" expects \d+ type argument',
        r'(.+\.py):\d+: error: "Future" expects \d+ type argument',
        r'(.+\.py):\d+: error: "Queue" expects \d+ type argument',
        r'(.+\.py):\d+: error: "Deque" expects \d+ type argument',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, mypy_output, re.MULTILINE)
        files.update(matches)

    return sorted(files)


def main():
    """Main function to run mypy and fix generic type errors"""
    # Change to project root
    project_root = Path(__file__).parent.parent.parent.parent
    os.chdir(project_root)

    print("Running mypy to find generic type errors...")

    # Run mypy
    result = subprocess.run(
        ["python", "-m", "mypy", "app/engine", "--show-error-codes"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Extract files with generic type errors
    files_to_fix = extract_generic_type_errors(result.stdout)

    if not files_to_fix:
        print("No generic type errors found!")
        return

    print(f"\nFound {len(files_to_fix)} files with generic type errors")

    fixed_count = 0
    for file_path in files_to_fix:
        print(f"Fixing {file_path}...")
        if fix_file_generic_types(file_path):
            fixed_count += 1
            print("  ✓ Fixed")
        else:
            print("  - No changes needed")

    print(f"\n✅ Fixed {fixed_count} files")

    # Run mypy again to check results
    print("\nRunning mypy again to verify fixes...")
    result = subprocess.run(
        ["python", "-m", "mypy", "app/engine", "--show-error-codes"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Count remaining generic type errors
    remaining_errors = len(extract_generic_type_errors(result.stdout))

    if remaining_errors == 0:
        print("✨ All generic type errors have been fixed!")
    else:
        print(f"⚠️  Still {remaining_errors} files with generic type errors remaining")
        print("These may require manual intervention")


if __name__ == "__main__":
    main()
