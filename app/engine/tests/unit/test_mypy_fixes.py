"""
Comprehensive test suite for fixing mypy errors using TDD.
This tracks progress as we fix each category of errors.
"""

from collections import defaultdict
from pathlib import Path
import os
import subprocess
import sys
from typing import NamedTuple

import pytest

if os.getenv("RUN_MYPY_PROGRESS_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("Mypy progress tests are opt-in (set RUN_MYPY_PROGRESS_TESTS=1)", allow_module_level=True)

pytest.importorskip("mypy")


class MypyError(NamedTuple):
    """Represents a single mypy error."""

    file: str
    line: int
    error_type: str
    message: str


def parse_mypy_output(output: str) -> list[MypyError]:
    """Parse mypy output into structured errors."""
    errors = []
    for line in output.strip().split("\n"):
        if ": error:" in line and not line.startswith("Found"):
            parts = line.split(":", 3)
            if len(parts) >= 4:
                file_path = parts[0]
                line_num = int(parts[1]) if parts[1].isdigit() else 0
                error_msg = parts[3].strip()

                # Extract error type from brackets
                error_type = "unknown"
                if "[" in error_msg and "]" in error_msg:
                    start = error_msg.rfind("[")
                    end = error_msg.rfind("]")
                    error_type = error_msg[start + 1 : end]
                    error_msg = error_msg[:start].strip()

                errors.append(MypyError(file_path, line_num, error_type, error_msg))
    return errors


def run_mypy_on_engine() -> tuple[bool, list[MypyError]]:
    """Run mypy on entire engine module."""
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        "app/engine",
        "--config-file=app/engine/mypy.ini",
        "--no-error-summary",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd="/Users/subhajlimanond/dev/online trader"
    )

    errors = parse_mypy_output(result.stdout)
    return result.returncode == 0, errors


def categorize_errors(errors: list[MypyError]) -> dict[str, list[MypyError]]:
    """Categorize errors by type."""
    categories = defaultdict(list)
    for error in errors:
        categories[error.error_type].append(error)
    return dict(categories)


class TestMypyProgress:
    """Track progress fixing mypy errors."""

    def test_syntax_errors_fixed(self) -> None:
        """Verify no syntax errors remain."""
        success, errors = run_mypy_on_engine()
        syntax_errors = [e for e in errors if e.error_type == "syntax"]

        # This should pass since we fixed the syntax error
        assert len(syntax_errors) == 0, f"Found {len(syntax_errors)} syntax errors"

    def test_missing_any_imports(self) -> None:
        """Track files missing 'Any' import."""
        success, errors = run_mypy_on_engine()
        any_errors = [e for e in errors if 'Name "Any" is not defined' in e.message]

        # Group by file
        files_needing_any: dict[str, list[object]] = {}
        for error in any_errors:
            if error.file not in files_needing_any:
                files_needing_any[error.file] = []
            files_needing_any[error.file].append(error.line)

        # After import fixer, no files should need Any import
        assert len(files_needing_any) == 0

        # Print summary for fixing
        print(f"\nFiles needing 'Any' import: {len(files_needing_any)}")
        for file, lines in sorted(files_needing_any.items())[:5]:
            print(f"  {file}: lines {sorted(set(lines))[:3]}...")  # type: ignore[type-var]

    def test_missing_callable_imports(self) -> None:
        """Track files missing 'Callable' import."""
        success, errors = run_mypy_on_engine()
        callable_errors = [e for e in errors if 'Name "Callable" is not defined' in e.message]

        files_needing_callable = set(e.file for e in callable_errors)

        # After import fixer, no files should need Callable
        assert len(files_needing_callable) == 0
        print("\nFiles needing 'Callable' import: 0")

    def test_type_annotation_errors(self) -> None:
        """Track missing type annotations."""
        success, errors = run_mypy_on_engine()
        annotation_errors = [e for e in errors if e.error_type == "var-annotated"]

        # Group by pattern
        conn_annotations = [
            e for e in annotation_errors if 'Need type annotation for "conn"' in e.message
        ]

        print(f"\nMissing type annotations: {len(annotation_errors)}")
        print(f"  Connection objects: {len(conn_annotations)}")

        assert success
        assert len(annotation_errors) == 0

    def test_error_categories(self) -> None:
        """Show all error categories for planning fixes."""
        success, errors = run_mypy_on_engine()
        categories = categorize_errors(errors)

        print(f"\nMypy error summary ({len(errors)} total):")
        for error_type, error_list in sorted(categories.items(), key=lambda x: -len(x[1])):
            print(f"  {error_type}: {len(error_list)} errors")

        assert success
        assert len(errors) == 0
        assert categories == {}


class TestSpecificFixes:
    """Test specific fixes we'll implement."""

    @pytest.fixture
    def test_file_path(self, tmp_path: Path) -> Path:
        """Create a temporary test file."""
        return tmp_path / "test_file.py"

    def test_any_import_fix(self, test_file_path: Path) -> None:
        """Test adding Any import to a file."""
        # Write file missing Any import
        test_file_path.write_text("""
from dataclasses import dataclass

@dataclass
class Config:
    data: dict[str, Any]  # Any not imported
""")

        # Add import
        content = test_file_path.read_text()
        if "from typing import" in content:
            # Add to existing import
            content = content.replace("from typing import", "from typing import Any, ")
        else:
            # Add new import
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.strip() and not line.startswith("#"):
                    lines.insert(i, "from typing import Any\n")
                    break
            content = "\n".join(lines)

        test_file_path.write_text(content)

        # Verify import added
        assert "from typing import Any" in test_file_path.read_text()

    def test_connection_annotation_fix(self, test_file_path: Path) -> None:
        """Test adding type annotation for connection objects."""
        # Pattern we see in errors
        test_file_path.write_text("""
import asyncpg

async def get_data():
    async with pool.acquire() as conn:  # Missing annotation
        return await conn.fetch("SELECT 1")
""")

        # Fix by adding annotation
        fixed_content = """
import asyncpg

async def get_data():
    async with pool.acquire() as conn:  # type: asyncpg.Connection
        return await conn.fetch("SELECT 1")
"""

        test_file_path.write_text(fixed_content)
        assert "type: asyncpg.Connection" in test_file_path.read_text()


if __name__ == "__main__":
    # Run this to see current error summary
    success, errors = run_mypy_on_engine()
    categories = categorize_errors(errors)

    print(f"Total mypy errors: {len(errors)}")
    print("\nTop error categories:")
    for error_type, error_list in sorted(categories.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {error_type}: {len(error_list)} errors")

    print("\nTop files with errors:")
    file_errors: dict[str, int] = defaultdict(int)
    for error in errors:
        file_errors[error.file] += 1

    for file, count in sorted(file_errors.items(), key=lambda x: -x[1])[:10]:
        print(f"  {file}: {count} errors")
