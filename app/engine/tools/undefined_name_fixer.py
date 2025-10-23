"""Tool to fix undefined name errors (Any, Decimal) in Python files."""

from pathlib import Path
import re


class UndefinedNameFixer:
    """Fixes undefined name errors by adding missing imports."""

    @staticmethod
    def fix_undefined_names(content: str) -> str:
        """Fix undefined names by adding necessary imports."""
        if not content.strip():
            return content

        lines = content.split("\n")

        # Check what needs to be imported
        needs_any = UndefinedNameFixer._needs_any(content)
        needs_decimal = UndefinedNameFixer._needs_decimal(content)

        if not needs_any and not needs_decimal:
            return content

        # Find existing imports
        has_typing_import, typing_line_idx, typing_imports = UndefinedNameFixer._find_typing_import(lines)
        has_decimal_import = UndefinedNameFixer._has_decimal_import(lines)

        # Add imports as needed
        result_lines = []
        import_added = False

        for i, line in enumerate(lines):
            if i == typing_line_idx and needs_any and "Any" not in typing_imports:
                # Add Any to existing typing import
                if typing_imports:
                    new_imports = ["Any"] + typing_imports
                    new_imports.sort()
                    result_lines.append(f"from typing import {', '.join(new_imports)}")
                    # Check if we also need to add Decimal after this
                    if needs_decimal and not has_decimal_import:
                        result_lines.append("from decimal import Decimal")
                        # Mark that we've handled the imports
                        import_added = True
                else:
                    result_lines.append("from typing import Any")
            elif not import_added and UndefinedNameFixer._is_import_location(lines, i):
                # Add new imports at the appropriate location
                if needs_decimal and not has_decimal_import:
                    result_lines.append("from decimal import Decimal")
                    if not has_typing_import and needs_any:
                        result_lines.append("from typing import Any")
                    import_added = True
                    result_lines.append("")  # blank line after imports
                    result_lines.append("")  # second blank line
                    result_lines.append(line)
                elif not has_typing_import and needs_any:
                    result_lines.append("from typing import Any")
                    import_added = True
                    result_lines.append("")  # blank line after imports
                    result_lines.append("")  # second blank line
                    result_lines.append(line)
                else:
                    result_lines.append(line)
            else:
                result_lines.append(line)

        # If no imports were added and we need them, add at the beginning
        if not import_added:
            new_imports = []
            if needs_decimal and not has_decimal_import:
                new_imports.append("from decimal import Decimal")
            if needs_any and not has_typing_import:
                new_imports.append("from typing import Any")

            if new_imports:
                # Find the first non-comment, non-docstring line
                insert_idx = 0
                in_docstring = False
                for i, line in enumerate(result_lines):
                    stripped = line.strip()
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        if in_docstring:
                            in_docstring = False
                            insert_idx = i + 1
                        else:
                            in_docstring = True
                    elif not in_docstring and stripped and not stripped.startswith("#"):
                        insert_idx = i
                        break

                # Insert imports
                for i, imp in enumerate(reversed(new_imports)):
                    result_lines.insert(insert_idx, imp)

                # Add blank lines after imports only if there's code after
                if insert_idx < len(result_lines) - len(new_imports):
                    result_lines.insert(insert_idx + len(new_imports), "")
                    result_lines.insert(insert_idx + len(new_imports) + 1, "")

        return "\n".join(result_lines)

    @staticmethod
    def _needs_any(content: str) -> bool:
        """Check if the file uses Any without importing it."""
        # Look for Any used in type annotations
        patterns = [
            r": Any[^a-zA-Z]",  # Type annotation
            r"-> Any[^a-zA-Z]",  # Return type
            r"\[Any\b",  # In generics (e.g., dict[Any, ...], list[Any])
            r"\bAny\]",  # In generics (e.g., dict[..., Any])
            r", Any[,\)]",  # In function args
            r"\(Any[,\)]",  # At start of args
            r"\bAny\s*\|",  # In union types
            r"\|\s*Any\b",  # In union types
        ]

        for pattern in patterns:
            if re.search(pattern, content):
                # Check if Any is already imported
                if not re.search(r"from typing import.*\bAny\b", content):
                    return True
        return False

    @staticmethod
    def _needs_decimal(content: str) -> bool:
        """Check if the file uses Decimal without importing it."""
        # Look for Decimal used in code
        patterns = [
            r": Decimal[^a-zA-Z]",  # Type annotation
            r"-> Decimal[^a-zA-Z]",  # Return type
            r"Decimal\(",  # Constructor call
            r"\[Decimal\]",  # Generic type
        ]

        for pattern in patterns:
            if re.search(pattern, content):
                # Check if Decimal is already imported
                if not re.search(r"from decimal import.*\bDecimal\b", content):
                    return True
        return False

    @staticmethod
    def _find_typing_import(lines: list[str]) -> tuple[bool, int, list[str]]:
        """Find existing typing import and return its details."""
        for i, line in enumerate(lines):
            match = re.match(r"from typing import (.+)", line)
            if match:
                imports_str = match.group(1)
                imports = [imp.strip() for imp in imports_str.split(",")]
                return True, i, imports
        return False, -1, []

    @staticmethod
    def _has_decimal_import(lines: list[str]) -> bool:
        """Check if Decimal is already imported."""
        for line in lines:
            if re.match(r"from decimal import.*\bDecimal\b", line):
                return True
        return False

    @staticmethod
    def _is_import_location(lines: list[str], current_idx: int) -> bool:
        """Determine if this is a good location to insert imports."""
        if current_idx >= len(lines):
            return False

        current_line = lines[current_idx].strip()

        # After existing imports
        if current_idx > 0:
            prev_line = lines[current_idx - 1].strip()
            if (prev_line.startswith("from ") or prev_line.startswith("import ")) and not current_line.startswith(("from ", "import ")):
                return True

        # Before first function/class definition
        if current_line.startswith(("def ", "class ", "@")):
            return True

        return False

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix undefined names in a file."""
        with open(file_path) as f:
            content = f.read()

        fixed_content = UndefinedNameFixer.fix_undefined_names(content)

        if fixed_content != content:
            with open(file_path, "w") as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_undefined_names(directory: str) -> list[str]:
        """Find all Python files with undefined name errors."""
        files_with_errors = []

        for py_file in Path(directory).rglob("*.py"):
            with open(py_file) as f:
                content = f.read()

            if UndefinedNameFixer._needs_any(content) or UndefinedNameFixer._needs_decimal(content):
                files_with_errors.append(str(py_file))

        return files_with_errors

    @staticmethod
    def fix_all_files(directory: str) -> int:
        """Fix all files with undefined name errors in a directory."""
        files_with_errors = UndefinedNameFixer.get_files_with_undefined_names(directory)

        for file_path in files_with_errors:
            print(f"Fixing undefined names in {file_path}")
            UndefinedNameFixer.fix_file(file_path)

        return len(files_with_errors)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "app/engine"

    fixed_count = UndefinedNameFixer.fix_all_files(directory)
    print(f"Fixed {fixed_count} files")
