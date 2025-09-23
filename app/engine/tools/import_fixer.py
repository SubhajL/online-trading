"""
Automatic import fixer for mypy errors.
Fixes missing imports from typing module.
"""

import re
from collections import defaultdict
from pathlib import Path


def detect_missing_imports(mypy_output: str) -> dict[Path, set[str]]:
    """
    Parse mypy output to find missing imports.
    Returns dict mapping file paths to sets of missing type names.
    """
    result = defaultdict(set)

    # Pattern to match mypy name-defined errors
    # Example: app/engine/core/error_handling.py:52: error:
    # Name "Any" is not defined  [name-defined]
    error_pattern = re.compile(
        r'^(.+?):(\d+):\s*error:\s*Name\s*"(\w+)"\s*is\s*not\s*defined\s*'
        r'\[name-defined\]'
    )

    # Track which types are from typing module
    typing_types = {
        'Any', 'Callable', 'Optional', 'Union', 'List', 'Dict', 'Tuple',
        'Set', 'Type', 'TypeVar', 'Generic', 'Protocol', 'Literal',
        'Final', 'TypedDict', 'Annotated', 'TypeAlias'
    }

    lines = mypy_output.strip().split('\n')

    for i, line in enumerate(lines):
        match = error_pattern.match(line)
        if match:
            file_path = Path(match.group(1))
            type_name = match.group(3)

            # Check if this is a typing module type
            if type_name in typing_types:
                result[file_path].add(type_name)
            elif i + 1 < len(lines):
                # Check next line for suggestion
                next_line = lines[i + 1]
                if 'typing' in next_line and type_name in next_line:
                    result[file_path].add(type_name)

    return dict(result)  # Convert defaultdict to regular dict


def add_missing_imports(file_path: Path, imports_needed: set[str]) -> bool:
    """
    Add missing imports to a file.
    Returns True if file was modified.
    """
    if not file_path.exists():
        return False

    content = file_path.read_text()
    lines = content.split('\n')

    # Find existing typing imports
    existing_imports = set()
    typing_import_line_idx = -1
    typing_import_pattern = re.compile(r'^\s*from\s+typing\s+import\s+(.+)$')

    for i, line in enumerate(lines):
        match = typing_import_pattern.match(line)
        if match:
            typing_import_line_idx = i
            # Parse existing imports
            imports_str = match.group(1)
            # Handle multi-line imports by removing line continuations
            imports_str = (imports_str.replace('\\', '')
                           .replace('(', '').replace(')', ''))
            # Split by comma and strip whitespace
            for imp in imports_str.split(','):
                imp = imp.strip()
                if imp:
                    existing_imports.add(imp)
            break

    # Check what actually needs to be added
    to_add = imports_needed - existing_imports
    if not to_add:
        return False  # Nothing to add

    if typing_import_line_idx >= 0:
        # Merge with existing import
        all_imports = sorted(existing_imports | to_add)
        new_import_line = f"from typing import {', '.join(all_imports)}"
        lines[typing_import_line_idx] = new_import_line
    else:
        # Add new import line
        # Find where to insert (after __future__ imports if any)
        insert_idx = 0
        future_idx = -1
        first_code_idx = -1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('from __future__'):
                future_idx = i
            elif (stripped and not stripped.startswith('#')
                  and not stripped.startswith('"""')):
                if first_code_idx == -1:
                    first_code_idx = i
                    break

        if future_idx >= 0:
            insert_idx = future_idx + 1
            # Skip blank lines after __future__
            while insert_idx < len(lines) and not lines[insert_idx].strip():
                insert_idx += 1
        else:
            # Check for module docstring
            if lines and lines[0].strip().startswith('"""'):
                # Find end of docstring
                for i in range(1, len(lines)):
                    if '"""' in lines[i]:
                        insert_idx = i + 1
                        break
            insert_idx = max(0, insert_idx)

        # Add the import
        all_imports = sorted(to_add)
        new_import_line = f"from typing import {', '.join(all_imports)}"

        # Add with appropriate spacing
        if insert_idx < len(lines):
            # Check if we need blank lines
            if insert_idx > 0 and lines[insert_idx - 1].strip():
                lines.insert(insert_idx, "")
                insert_idx += 1
            lines.insert(insert_idx, new_import_line)
            if insert_idx + 1 < len(lines) and lines[insert_idx + 1].strip():
                lines.insert(insert_idx + 1, "")
        else:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(new_import_line)

    # Write back
    file_path.write_text('\n'.join(lines))
    return True


def fix_all_import_errors(engine_path: Path) -> tuple[int, int]:
    """
    Run mypy and fix all missing import errors.
    Returns (files_fixed, imports_added).
    """
    import subprocess
    import sys

    # Run mypy on the engine
    mypy_cmd = [
        sys.executable,
        "-m",
        "mypy",
        str(engine_path),
        f"--config-file={engine_path / 'mypy.ini'}",
        "--no-error-summary"
    ]

    result = subprocess.run(mypy_cmd, capture_output=True, text=True)
    mypy_output = result.stdout

    # Detect missing imports
    missing_imports = detect_missing_imports(mypy_output)

    if not missing_imports:
        return (0, 0)

    files_fixed = 0
    total_imports_added = 0

    # Fix each file
    for file_path, imports_needed in missing_imports.items():
        if add_missing_imports(file_path, imports_needed):
            files_fixed += 1
            total_imports_added += len(imports_needed)
            print(f"Fixed {file_path}: added "
                  f"{', '.join(sorted(imports_needed))}")

    return (files_fixed, total_imports_added)
