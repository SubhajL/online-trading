#!/usr/bin/env python3
"""
Script to help resolve merge conflicts by combining both changes.
Strategy: Keep Python 3.9+ type hints from svc/features but also incorporate mypy fixes.
"""

import re
import sys
from pathlib import Path

def resolve_imports(content: str) -> str:
    """Resolve import conflicts by keeping the Python 3.9+ style."""
    # Remove old-style typing imports that are now built-in
    content = re.sub(r'from typing import List, Any, Optional, Tuple\n', '', content)
    content = re.sub(r'from typing import Dict, Any, Optional\n', '', content)
    content = re.sub(r'from typing import Optional, Dict, Any\n', '', content)
    content = re.sub(r'from typing import Optional, List, Dict, Any\n', '', content)

    # Keep only necessary typing imports
    if 'from typing import' in content and 'Union' not in content and 'Literal' not in content:
        # Remove unnecessary typing imports for built-in types
        content = re.sub(r'from typing import .*\n', '', content)

    return content

def resolve_type_annotations(content: str) -> str:
    """Convert List[T] -> list[T], Dict[K,V] -> dict[K,V], etc."""
    # Replace List[X] with list[X]
    content = re.sub(r'\bList\[', 'list[', content)
    # Replace Dict[X, Y] with dict[X, Y]
    content = re.sub(r'\bDict\[', 'dict[', content)
    # Replace Tuple[X, ...] with tuple[X, ...]
    content = re.sub(r'\bTuple\[', 'tuple[', content)
    # Replace Optional[X] with X | None
    content = re.sub(r'Optional\[([^\]]+)\]', r'\1 | None', content)

    return content

def process_conflict_file(filepath: Path) -> None:
    """Process a file with merge conflicts."""
    print(f"Processing {filepath}...")

    with open(filepath, 'r') as f:
        content = f.read()

    if '<<<<<<< HEAD' not in content:
        print(f"  No conflicts found in {filepath}")
        return

    # For each conflict, we'll generally prefer HEAD (svc/features) but incorporate type fixes
    conflicts = re.findall(r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> origin/main', content, re.DOTALL)

    for head_content, main_content in conflicts:
        # Special handling for import conflicts
        if 'from typing import' in main_content and 'from typing import' not in head_content:
            # Skip the import - we're using Python 3.9+ built-ins
            content = content.replace(f'<<<<<<< HEAD\n{head_content}\n=======\n{main_content}\n>>>>>>> origin/main', head_content)
        elif 'list[' in head_content.lower() and 'List[' in main_content:
            # Keep the Python 3.9+ style from HEAD
            content = content.replace(f'<<<<<<< HEAD\n{head_content}\n=======\n{main_content}\n>>>>>>> origin/main', head_content)
        elif 'assert' in main_content and 'assert' not in head_content:
            # Incorporate the assertion from main
            combined = head_content + '\n' + main_content
            content = content.replace(f'<<<<<<< HEAD\n{head_content}\n=======\n{main_content}\n>>>>>>> origin/main', combined)
        else:
            # Default: prefer HEAD but check if we need type annotations from main
            if 'None' in main_content and 'None' not in head_content:
                # Might need to incorporate None handling
                print(f"  Manual review needed for conflict in {filepath}")
            content = content.replace(f'<<<<<<< HEAD\n{head_content}\n=======\n{main_content}\n>>>>>>> origin/main', head_content)

    # Clean up any remaining imports
    content = resolve_imports(content)

    # Apply Python 3.9+ type annotations
    content = resolve_type_annotations(content)

    with open(filepath, 'w') as f:
        f.write(content)

    print(f"  Resolved {filepath}")

if __name__ == "__main__":
    # Get all files with merge conflicts
    import subprocess
    result = subprocess.run(['git', 'diff', '--name-only', '--diff-filter=U'],
                          capture_output=True, text=True)

    conflict_files = [Path(f) for f in result.stdout.strip().split('\n') if f]

    print(f"Found {len(conflict_files)} files with conflicts")

    for filepath in conflict_files:
        try:
            process_conflict_file(filepath)
        except Exception as e:
            print(f"  Error processing {filepath}: {e}")