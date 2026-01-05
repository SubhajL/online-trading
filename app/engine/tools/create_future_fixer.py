"""Tool to fix loop.create_future() calls that don't exist in the asyncio module."""

from pathlib import Path
import re


class CreateFutureFixer:
    """Fixes loop.create_future() calls by using loop.create_future()."""

    @staticmethod
    def fix_create_future(content: str) -> str:
        """Fix loop.create_future() calls in the given content."""
        if not content.strip():
            return content

        # Check if there are any loop.create_future() calls
        if "loop.create_future()" not in content:
            return content

        lines = content.split("\n")
        result_lines = []

        # Track if we've seen a function/method definition
        current_function_indent = None
        loop_var_added = False
        existing_loop_var = None

        for i, line in enumerate(lines):
            # Detect function/method definitions
            if re.match(r"^(\s*)(async\s+)?def\s+", line):
                match = re.match(r"^(\s*)", line)
                current_function_indent = len(match.group(1))
                loop_var_added = False
                existing_loop_var = None

            # Check if there's already a loop variable
            if existing_loop_var is None and "asyncio.get_event_loop()" in line:
                match = re.match(r"^(\s*)(\w+)\s*=\s*asyncio\.get_event_loop\(\)", line)
                if match:
                    existing_loop_var = match.group(2)
            elif existing_loop_var is None and "asyncio.get_running_loop()" in line:
                match = re.match(
                    r"^(\s*)(\w+)\s*=\s*asyncio\.get_running_loop\(\)", line,
                )
                if match:
                    existing_loop_var = match.group(2)

            # Fix loop.create_future() calls
            if "loop.create_future()" in line:
                # Determine the indentation
                match = re.match(r"^(\s*)", line)
                indent = match.group(1)

                # If we have an existing loop variable, use it
                if existing_loop_var:
                    fixed_line = line.replace(
                        "loop.create_future()", f"{existing_loop_var}.create_future()",
                    )
                    result_lines.append(fixed_line)
                else:
                    # Need to add loop = asyncio.get_event_loop() before this line
                    if not loop_var_added:
                        result_lines.append(f"{indent}loop = asyncio.get_event_loop()")
                        loop_var_added = True
                        existing_loop_var = "loop"

                    fixed_line = line.replace(
                        "loop.create_future()", "loop.create_future()",
                    )
                    result_lines.append(fixed_line)
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    @staticmethod
    def fix_file(file_path: str) -> None:
        """Fix create_future calls in a file."""
        with open(file_path) as f:
            content = f.read()

        fixed_content = CreateFutureFixer.fix_create_future(content)

        if fixed_content != content:
            with open(file_path, "w") as f:
                f.write(fixed_content)

    @staticmethod
    def get_files_with_create_future_errors(directory: str) -> list[str]:
        """Find all Python files with loop.create_future() calls."""
        files_with_errors = []

        for py_file in Path(directory).rglob("*.py"):
            # Skip virtual environment and test directories
            if ".venv" in py_file.parts or "venv" in py_file.parts:
                continue

            try:
                with open(py_file) as f:
                    content = f.read()

                if "loop.create_future()" in content:
                    files_with_errors.append(str(py_file))
            except Exception:
                # Skip files that can't be read
                pass

        return files_with_errors

    @staticmethod
    def fix_all_files(directory: str) -> int:
        """Fix all files with create_future errors in a directory."""
        files_with_errors = CreateFutureFixer.get_files_with_create_future_errors(
            directory,
        )

        for file_path in files_with_errors:
            print(f"Fixing create_future in {file_path}")
            CreateFutureFixer.fix_file(file_path)

        return len(files_with_errors)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "app/engine"

    fixed_count = CreateFutureFixer.fix_all_files(directory)
    print(f"Fixed {fixed_count} files")
