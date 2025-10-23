"""Tool to fix broken import syntax where 'from module' part is missing."""

from pathlib import Path
import re


class ImportSyntaxFixer:
    """Fixes import statements missing the 'from module' part."""

    @staticmethod
    def fix_imports(content: str) -> str:
        """Fix broken import statements in the given content."""
        lines = content.split("\n")
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check if this line starts with 'from' followed by spaces and then an uppercase letter
            # This indicates a broken import where module name is missing
            if re.match(r"^from\s+[A-Z]", line):
                # Extract the import items
                import_items = line[4:].strip()  # Remove 'from ' prefix

                # Check if this is a multi-line import
                if i + 1 < len(lines) and (lines[i + 1].strip().startswith(",") or
                                          (lines[i + 1].strip() and not lines[i + 1].strip().startswith(("from", "import")))):
                    # Multi-line import
                    result_lines.append("from ..config import (")
                    result_lines.append("    " + import_items)

                    # Continue adding lines until we find the closing parenthesis
                    i += 1
                    while i < len(lines):
                        result_lines.append(lines[i])
                        if ")" in lines[i]:
                            break
                        i += 1
                else:
                    # Single line import
                    result_lines.append(f"from ..config import {import_items}")
            else:
                result_lines.append(line)

            i += 1

        return "\n".join(result_lines)

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix import syntax in a file."""
        with open(file_path) as f:
            content = f.read()

        fixed_content = ImportSyntaxFixer.fix_imports(content)

        if fixed_content != content:
            with open(file_path, "w") as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_import_errors(directory: str) -> list[str]:
        """Find all Python files with import syntax errors."""
        files_with_errors = []

        for py_file in Path(directory).rglob("*.py"):
            with open(py_file) as f:
                content = f.read()

            # Look for lines that start with 'from' followed by spaces and uppercase letters
            # This pattern indicates broken imports where the module path is missing
            if re.search(r"^from\s+[A-Z]", content, re.MULTILINE):
                files_with_errors.append(str(py_file))

        return files_with_errors

    @staticmethod
    def fix_all_files(directory: str) -> int:
        """Fix all files with import syntax errors in a directory."""
        files_with_errors = ImportSyntaxFixer.get_files_with_import_errors(directory)

        for file_path in files_with_errors:
            print(f"Fixing imports in {file_path}")
            ImportSyntaxFixer.fix_file(file_path)

        return len(files_with_errors)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "app/engine"

    fixed_count = ImportSyntaxFixer.fix_all_files(directory)
    print(f"Fixed {fixed_count} files")
