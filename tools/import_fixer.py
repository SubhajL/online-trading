"""Standalone import fixer utilities for tests without engine imports.

Provides two main entry points:
- detect_missing_imports(mypy_output: str) -> dict[Path, set[str]]
- add_missing_imports(path: Path, names: set[str]) -> bool
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Set
import re


def detect_missing_imports(mypy_output: str) -> Dict[Path, Set[str]]:
    """Parse mypy stdout and group missing typing imports by file.

    Looks for "Name \"X\" is not defined  [name-defined]" lines and returns
    a mapping of file -> set of missing names (e.g., {Path('file.py'): {'Any'}}).
    """
    result: Dict[Path, Set[str]] = {}
    for line in mypy_output.splitlines():
        line = line.strip()
        if not line or ': error:' not in line:
            continue
        # Extract file path and error message
        parts = line.split(':', 3)
        if len(parts) < 4:
            continue
        file_path = parts[0]
        msg = parts[3]
        # Only name-defined
        if 'Name "' in msg and '[name-defined]' in msg:
            m = re.search(r'Name \"([A-Za-z_][A-Za-z0-9_]*)\" is not defined', msg)
            if not m:
                continue
            name = m.group(1)
            p = Path(file_path)
            names = result.setdefault(p, set())
            names.add(name)
    return result


def add_missing_imports(path: Path, names: Set[str]) -> bool:
    """Insert or merge "from typing import ..." with the given names.

    - Merges into existing typing import if present.
    - Inserts after module docstring and any __future__ import lines.
    - Returns True if file content was modified.
    """
    original = path.read_text() if path.exists() else ''
    if not names:
        return False

    lines = original.split('\n')

    # Remove names already imported from typing
    existing_typing_imports = set()
    for line in lines:
        if line.startswith('from typing import'):
            after = line.split('import', 1)[1]
            for item in after.split(','):
                existing_typing_imports.add(item.strip())

    missing = {n for n in names if n not in existing_typing_imports}
    if not missing:
        return False

    # Find insertion index: after docstring, after __future__ imports, and after existing imports if any
    insert_at = 0
    # Skip docstring
    if lines and lines[0].lstrip().startswith('"""'):
        for i in range(1, len(lines)):
            if lines[i].rstrip().endswith('"""'):
                insert_at = i + 1
                break

    # Gather import lines (including from __future__)
    future_end = insert_at
    for i in range(insert_at, len(lines)):
        if lines[i].startswith('from __future__ import'):
            future_end = i + 1
        else:
            break

    insert_at = max(insert_at, future_end)

    # If there's an existing 'from typing import', merge there
    for idx, line in enumerate(lines):
        if line.startswith('from typing import'):
            # Merge missing names, keep alphabetical
            after = line.split('import', 1)[1]
            current = [x.strip() for x in after.split(',') if x.strip()]
            merged = sorted(set(current).union(missing))
            lines[idx] = f"from typing import {', '.join(merged)}"
            new_content = '\n'.join(lines)
            if new_content != original:
                path.write_text(new_content)
                return True
            return False

    # No existing typing import, insert a new one after future imports/docstring
    insertion = f"from typing import {', '.join(sorted(missing))}"
    lines.insert(insert_at, insertion)
    new_content = '\n'.join(lines)
    if new_content != original:
        path.write_text(new_content)
        return True
    return False

