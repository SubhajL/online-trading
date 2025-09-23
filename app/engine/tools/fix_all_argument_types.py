#!/usr/bin/env python3
"""
Fix all missing function argument type annotations by running mypy and automatically fixing them
"""

import subprocess
import re
from pathlib import Path
from argument_type_fixer import fix_file_argument_types


def get_files_with_argument_type_errors():
    """Run mypy and extract files with missing argument type errors"""
    result = subprocess.run(
        ['python', '-m', 'mypy', 'app/engine'],
        capture_output=True,
        text=True
    )

    files_to_fix = set()

    # Look for missing argument type annotations
    for line in result.stdout.split('\n'):
        if 'Function is missing a type annotation for one or more arguments' in line:
            match = re.match(r'(app/engine/[^:]+):', line)
            if match:
                files_to_fix.add(match.group(1))

    return sorted(files_to_fix)


def fix_all_argument_type_annotations():
    """Fix argument type annotations in all files that need it"""
    files = get_files_with_argument_type_errors()

    if not files:
        print("No argument type annotation errors found!")
        return

    print(f"Found {len(files)} files with missing argument type annotations:")
    for file_path in files:
        print(f"  - {file_path}")

    print("\nFixing argument type annotations...")
    fixed_count = 0

    for file_path in files:
        if fix_file_argument_types(file_path):
            print(f"✓ Fixed {file_path}")
            fixed_count += 1
        else:
            print(f"✗ No changes needed in {file_path}")

    print(f"\nFixed {fixed_count} files")

    # Run mypy again to verify
    print("\nVerifying fixes...")
    result = subprocess.run(
        ['python', '-m', 'mypy', 'app/engine', '--no-error-summary'],
        capture_output=True,
        text=True
    )

    # Count remaining argument type errors
    remaining_errors = 0
    for line in result.stdout.split('\n'):
        if 'Function is missing a type annotation for one or more arguments' in line:
            remaining_errors += 1

    print(f"Remaining argument type annotation errors: {remaining_errors}")


if __name__ == '__main__':
    fix_all_argument_type_annotations()