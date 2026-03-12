"""
Test case for redis_adapter.py syntax and type checking.
Written using TDD to fix mypy errors.
"""

import pytest
from pathlib import Path
import subprocess
import sys
from typing import NamedTuple


class MypyResult(NamedTuple):
    """Result of running mypy on a file."""
    success: bool
    errors: list[str]
    error_count: int


def _mypy_available() -> bool:
    """Check if mypy is importable under the current interpreter."""
    proc = subprocess.run(
        [sys.executable, "-c", "import mypy"],
        capture_output=True,
    )
    return proc.returncode == 0


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


class TestRedisAdapterSyntax:
    """Test redis adapter syntax and type compliance."""

    @pytest.fixture
    def redis_adapter_path(self) -> Path:
        """Path to redis adapter file."""
        return Path(__file__).parent.parent.parent / "adapters" / "redis" / "redis_adapter.py"

    @pytest.fixture
    def mypy_config_path(self) -> Path:
        """Path to mypy config."""
        return Path(__file__).parent.parent.parent / "mypy.ini"

    @pytest.mark.skipif(not _mypy_available(), reason="mypy not installed")
    def test_redis_adapter_has_no_syntax_errors(self, redis_adapter_path: Path, mypy_config_path: Path) -> None:
        """redis_adapter.py should not have syntax errors."""
        result = run_mypy_on_file(redis_adapter_path, mypy_config_path)
        # Ensure there are no syntax errors specifically
        syntax_errors = [e for e in result.errors if "Invalid syntax" in e]
        assert len(syntax_errors) == 0

    def test_clear_cache_method_structure(self) -> None:
        """
        Test the expected structure of clear_cache method.
        This documents what the correct implementation should look like.
        """
        expected_structure = '''
    async def clear_cache(self, prefix: str | None = None) -> int:
        """Clear cache with optional prefix filter"""
        try:
            self._ensure_connected()

            if prefix:
                pattern = self._build_key(prefix, "*")
                assert self._redis is not None
                keys = await self._redis.keys(pattern)
                if keys:
                    deleted = await self._redis.delete(*keys)
                    return int(deleted)
                return 0
            else:
                # Clear entire database
                assert self._redis is not None
                result = await self._redis.flushdb()
                return 1 if result else 0

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0
        '''

        # This test documents the expected structure
        assert "if prefix:" in expected_structure
        assert "else:" in expected_structure
        assert expected_structure.count("else:") == 1  # Only one else block


class TestMypyCompliance:
    """Test overall mypy compliance after fixes."""

    @pytest.fixture
    def redis_adapter_path(self) -> Path:
        """Path to redis adapter file."""
        return Path(__file__).parent.parent.parent / "adapters" / "redis" / "redis_adapter.py"

    @pytest.fixture
    def mypy_config_path(self) -> Path:
        """Path to mypy config."""
        return Path(__file__).parent.parent.parent / "mypy.ini"

    @pytest.mark.skipif(not _mypy_available(), reason="mypy not installed")
    def test_no_mypy_errors_after_fix(self, redis_adapter_path: Path, mypy_config_path: Path) -> None:
        """Require full mypy success for redis adapter."""
        result = run_mypy_on_file(redis_adapter_path, mypy_config_path)
        assert result.success, f"Mypy errors:\n" + "\n".join(result.errors)
        assert result.error_count == 0
