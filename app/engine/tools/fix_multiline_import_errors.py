#!/usr/bin/env python3
"""
Fix incorrectly placed 'from typing import Any' inside multi-line imports
"""

import os
from pathlib import Path
import re


def fix_multiline_import_errors(file_path: str) -> bool:
    """Fix incorrect Any imports inside multi-line imports"""
    try:
        with open(file_path) as f:
            content = f.read()

        original_content = content

        # Pattern to find multi-line imports with incorrect Any import
        pattern = r"(from\s+[^\s]+\s+import\s+\(\s*\nfrom typing import Any\s*\n)"

        # Replace by removing the incorrect import line
        content = re.sub(
            pattern,
            r"from \g<1>".replace(r"\g<1>", "").replace("from typing import Any\n", ""),
            content,
        )

        # More specific pattern
        pattern = r"(from\s+[\w.]+\s+import\s+\()\s*\nfrom typing import Any\s*\n"
        content = re.sub(pattern, r"\1\n", content)

        if content != original_content:
            with open(file_path, "w") as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    """Find and fix all files with multiline import errors"""
    project_root = Path(__file__).parent.parent.parent.parent
    os.chdir(project_root)

    fixed_count = 0

    # Find all Python files
    for file_path in Path("app/engine").rglob("*.py"):
        if fix_multiline_import_errors(str(file_path)):
            print(f"Fixed: {file_path}")
            fixed_count += 1

    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
