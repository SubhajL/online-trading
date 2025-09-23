"""
Fix missing type annotations for database connections.
Handles asyncpg and Redis connection patterns.
"""

import re
from pathlib import Path
from typing import List, Dict, Any


def detect_connection_patterns(content: str) -> List[Dict[str, Any]]:
    """
    Detect patterns where connection type annotations are missing

    Args:
        content: Python source code

    Returns:
        List of patterns that need type annotations
    """
    patterns = []
    lines = content.split('\n')

    # Pattern 1: async context manager with -> None that should return AsyncIterator
    asynccontextmanager_pattern = re.compile(
        r'^\s*@asynccontextmanager\s*$'
    )
    get_connection_pattern = re.compile(
        r'^\s*async\s+def\s+get_connection\(.*\)\s*->\s*None\s*:'
    )

    for i, line in enumerate(lines):
        # Check for @asynccontextmanager followed by get_connection -> None
        if asynccontextmanager_pattern.match(line):
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if get_connection_pattern.match(next_line):
                    patterns.append({
                        'type': 'async_context_manager',
                        'method': 'get_connection',
                        'line': i + 1,  # 0-based
                        'current_return': 'None'
                    })

    # Pattern 2: async with pool.acquire() as conn: without annotation
    pool_acquire_pattern = re.compile(
        r'^\s*async\s+with\s+.*\.(pool|_pool)\.acquire\(\)\s+as\s+(\w+)\s*:'
    )

    for i, line in enumerate(lines):
        match = pool_acquire_pattern.match(line)
        if match and '# ' not in line:  # Skip if already has comment annotation
            var_name = match.group(2)
            # Check if variable is already annotated (not just in "as var:")
            if not re.search(rf'\b{var_name}\s*:\s*\w+', line):
                patterns.append({
                    'type': 'connection_variable',
                    'variable': var_name,
                    'line': i
                })

    # Pattern 3: connection = await get_connection() without annotation
    await_connection_pattern = re.compile(
        r'^\s*(\w+)\s*=\s*await\s+.*\.get_connection\(\)'
    )

    for i, line in enumerate(lines):
        match = await_connection_pattern.match(line)
        if match:
            var_name = match.group(1)
            # Check if already has type annotation
            if not re.search(rf'\b{var_name}\s*:\s*\w+', line):
                patterns.append({
                    'type': 'await_get_connection',
                    'variable': var_name,
                    'line': i
                })

    return patterns


def add_connection_type_hints(code: str) -> str:
    """
    Add type hints for database connections

    Args:
        code: Python source code

    Returns:
        Code with added type annotations
    """
    patterns = detect_connection_patterns(code)
    if not patterns:
        return code

    lines = code.split('\n')
    modified_lines = lines.copy()

    # Track if we need to add imports
    needs_asynciterator = False
    has_asynciterator = 'AsyncIterator' in code
    has_asyncpg = 'import asyncpg' in code or 'from asyncpg' in code

    # Process patterns in reverse order to avoid line number shifts
    for pattern in sorted(patterns, key=lambda p: p['line'], reverse=True):
        if pattern['type'] == 'async_context_manager':
            # Replace -> None with -> AsyncIterator[asyncpg.Connection]
            line_idx = pattern['line']
            old_line = modified_lines[line_idx]
            new_line = old_line.replace('-> None', '-> AsyncIterator[asyncpg.Connection]')
            modified_lines[line_idx] = new_line
            needs_asynciterator = True

        elif pattern['type'] == 'connection_variable':
            # Add inline comment annotation for context manager variable
            line_idx = pattern['line']
            old_line = modified_lines[line_idx]
            # Add comment annotation after the colon
            var_name = pattern['variable']
            # Find the colon position and add comment after it
            colon_pos = old_line.find(':')
            if colon_pos > 0:
                new_line = old_line[:colon_pos + 1] + f'  # {var_name}: asyncpg.Connection'
                if len(old_line) > colon_pos + 1:
                    new_line += old_line[colon_pos + 1:]
                modified_lines[line_idx] = new_line

        elif pattern['type'] == 'await_get_connection':
            # Add type annotation to variable assignment
            line_idx = pattern['line']
            old_line = modified_lines[line_idx]
            var_name = pattern['variable']
            # Determine Connection type based on imports
            if 'from asyncpg import Connection' in code:
                conn_type = 'Connection'
            else:
                conn_type = 'asyncpg.Connection'
            new_line = old_line.replace(f'{var_name} =', f'{var_name}: {conn_type} =')
            modified_lines[line_idx] = new_line

    # Add missing imports if needed
    if needs_asynciterator and not has_asynciterator:
        # Find where to add the import
        import_added = False
        for i, line in enumerate(modified_lines):
            if line.startswith('from typing import'):
                # Add to existing typing import
                if 'AsyncIterator' not in line:
                    # Extract current imports
                    match = re.match(r'from typing import (.+)', line)
                    if match:
                        imports = match.group(1).strip()
                        new_imports = f'{imports}, AsyncIterator'
                        modified_lines[i] = f'from typing import {new_imports}'
                        import_added = True
                        break

        if not import_added:
            # Add new typing import after other imports
            for i, line in enumerate(modified_lines):
                if line.startswith('import ') or line.startswith('from '):
                    continue
                elif line.strip() == '':
                    continue
                else:
                    # Found first non-import line, insert before it
                    modified_lines.insert(i, 'from typing import AsyncIterator')
                    break

    return '\n'.join(modified_lines)


def fix_connection_annotations(code: str) -> str:
    """
    Main function to fix connection type annotations in code

    Args:
        code: Python source code

    Returns:
        Code with fixed connection annotations
    """
    return add_connection_type_hints(code)


def fix_file_connection_annotations(file_path: str) -> bool:
    """
    Fix connection annotations in a specific file

    Args:
        file_path: Path to Python file

    Returns:
        True if file was modified, False otherwise
    """
    try:
        with open(file_path, 'r') as f:
            original_code = f.read()

        fixed_code = fix_connection_annotations(original_code)

        if fixed_code != original_code:
            with open(file_path, 'w') as f:
                f.write(fixed_code)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False
