"""
Test infrastructure for mypy type checking compliance.

This module provides test cases that verify our code passes mypy checks
and helps catch type errors during development using TDD principles.
"""

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


class MypyResult(NamedTuple):
    """Result of running mypy on a file or module."""
    success: bool
    errors: list[str]
    error_count: int


def run_mypy_on_file(file_path: Path, config_file: Path) -> MypyResult:
    """Run mypy on a specific file and return results."""
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        str(file_path),
        f"--config-file={config_file}",
        "--no-error-summary"
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    errors = []
    if result.returncode != 0:
        errors = [
            line for line in result.stdout.strip().split('\n')
            if line and not line.startswith('Success:')
        ]

    return MypyResult(
        success=result.returncode == 0,
        errors=errors,
        error_count=len(errors)
    )


def run_mypy_on_module(module_path: Path, config_file: Path) -> MypyResult:
    """Run mypy on an entire module and return results."""
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        str(module_path),
        f"--config-file={config_file}",
        "--no-error-summary"
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    errors = []
    error_count = 0
    if result.returncode != 0:
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if line and 'error' in line:
                errors.append(line)
                error_count += 1

    return MypyResult(
        success=result.returncode == 0,
        errors=errors,
        error_count=error_count
    )


def assert_no_mypy_errors(file_or_module: Path, config_file: Path) -> None:
    """Assert that a file or module has no mypy errors."""
    if file_or_module.is_file():
        result = run_mypy_on_file(file_or_module, config_file)
    else:
        result = run_mypy_on_module(file_or_module, config_file)

    if not result.success:
        error_msg = f"Mypy found {result.error_count} errors:\n"
        error_msg += "\n".join(result.errors)
        raise AssertionError(error_msg)


def get_mypy_baseline(module_path: Path, config_file: Path) -> dict[str, int]:
    """Get baseline mypy error counts per file."""
    result = run_mypy_on_module(module_path, config_file)

    file_errors: dict[str, int] = {}
    for error in result.errors:
        # Extract filename from error line
        if ':' in error:
            parts = error.split(':')
            if len(parts) >= 2:
                filename = parts[0]
                if filename not in file_errors:
                    file_errors[filename] = 0
                file_errors[filename] += 1

    return file_errors


# Test fixtures for type checking
TEST_FILE_CORRECT_TYPES = '''
"""Example file with correct type annotations."""
from typing import Any


def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def process_data(data: dict[str, Any]) -> list[str]:
    """Process data and return keys."""
    return list(data.keys())


class DataProcessor:
    """Process data with proper types."""

    def __init__(self, name: str) -> None:
        self.name = name

    def process(self, items: list[int]) -> dict[str, int]:
        """Process items."""
        return {"count": len(items), "sum": sum(items)}
'''

TEST_FILE_INCORRECT_TYPES = '''
"""Example file with type errors."""
from typing import Dict, List  # Wrong import style


def add_numbers(a, b):  # Missing type annotations
    """Add two numbers."""
    return a + b


def process_data(data: Dict[str, Any]) -> List[str]:  # Old style annotations
    """Process data and return keys."""
    result: list[int] = data.keys()  # Type error: keys() returns KeysView[str]
    return result  # Type error: returning list[int] when list[str] expected


class DataProcessor:
    """Process data with type errors."""

    def __init__(self, name):  # Missing return type
        self.name = name

    def process(self, items: list[str]) -> dict[str, int]:
        """Process items."""
        # Type error: sum() doesn't work with strings
        return {"count": len(items), "sum": sum(items)}
'''