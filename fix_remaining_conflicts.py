#!/usr/bin/env python3
"""
Fix remaining merge conflicts by properly handling Python 3.9+ type annotations.
"""

import re
import sys
from pathlib import Path

def fix_conflict(filepath: Path) -> None:
    """Fix conflicts in a single file."""
    print(f"Fixing {filepath}...")

    with open(filepath, 'r') as f:
        content = f.read()

    if '<<<<<<< HEAD' not in content:
        return

    # Find all conflicts
    pattern = r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> origin/main'

    def resolve(match):
        head = match.group(1)
        main = match.group(2)

        # For typing imports, always prefer no import (Python 3.9+)
        if 'from typing import' in main and 'from typing import' not in head:
            return head

        # For list[X] vs List[X], prefer list[X]
        if 'list[' in head.lower() and 'List[' in main:
            return head

        # For variable type annotations, keep Python 3.9+ style
        if ': list[' in head and ': List[' in main:
            return head

        # For assertions, combine both
        if 'assert' in main and 'assert' not in head:
            return head + '\n            ' + main.strip()

        # Default: prefer HEAD
        return head

    # Replace all conflicts
    fixed = re.sub(pattern, resolve, content, flags=re.DOTALL)

    # Remove any remaining conflict markers
    fixed = re.sub(r'<<<<<<< HEAD\n', '', fixed)
    fixed = re.sub(r'\n=======\n', '\n', fixed)
    fixed = re.sub(r'\n>>>>>>> origin/main', '', fixed)

    with open(filepath, 'w') as f:
        f.write(fixed)

    print(f"  Fixed {filepath}")

# Find all Python files with conflicts
import subprocess
result = subprocess.run(['grep', '-l', '<<<<<<< HEAD'] +
                       list(Path('app/engine').rglob('*.py')),
                       capture_output=True, text=True)

conflict_files = [Path(f) for f in result.stdout.strip().split('\n') if f]

print(f"Found {len(conflict_files)} files with remaining conflicts")

for filepath in conflict_files:
    fix_conflict(filepath)