"""
Tests for automatic import fixing based on mypy output.
Following TDD principles from CLAUDE.md.
"""

import pytest
from pathlib import Path
from textwrap import dedent


class TestDetectMissingImports:
    """Test detection of missing imports from mypy output."""

    def test_detect_missing_imports_parses_any_errors(self) -> None:
        """Should detect Any import needs from mypy output."""
        mypy_output = dedent("""
            app/engine/core/error_handling.py:52: error: Name "Any" is not defined  [name-defined]
            app/engine/core/error_handling.py:52: note: Did you forget to import it from "typing"? (Suggestion: "from typing import Any")
            app/engine/core/error_handling.py:133: error: Name "Any" is not defined  [name-defined]
        """).strip()

        from app.engine.tools.import_fixer import detect_missing_imports

        result = detect_missing_imports(mypy_output)

        assert Path("app/engine/core/error_handling.py") in result
        assert "Any" in result[Path("app/engine/core/error_handling.py")]
        assert len(result[Path("app/engine/core/error_handling.py")]) == 1  # Deduplicated

    def test_detect_missing_imports_parses_callable_errors(self) -> None:
        """Should detect Callable import needs from mypy output."""
        mypy_output = dedent("""
            app/engine/core/error_handling.py:470: error: Name "Callable" is not defined  [name-defined]
            app/engine/core/error_handling.py:470: note: Did you forget to import it from "typing"? (Suggestion: "from typing import Callable")
        """).strip()

        from app.engine.tools.import_fixer import detect_missing_imports

        result = detect_missing_imports(mypy_output)

        assert Path("app/engine/core/error_handling.py") in result
        assert "Callable" in result[Path("app/engine/core/error_handling.py")]

    def test_detect_missing_imports_handles_multiple_files(self) -> None:
        """Should group missing imports by file."""
        mypy_output = dedent("""
            app/engine/adapters/redis/redis_adapter.py:132: error: Name "Any" is not defined  [name-defined]
            app/engine/adapters/router_client/http_client.py:99: error: Name "Any" is not defined  [name-defined]
            app/engine/adapters/router_client/http_client.py:147: error: Name "Any" is not defined  [name-defined]
            app/engine/adapters/redis/redis_adapter.py:186: error: Name "Any" is not defined  [name-defined]
        """).strip()

        from app.engine.tools.import_fixer import detect_missing_imports

        result = detect_missing_imports(mypy_output)

        assert len(result) == 2
        assert Path("app/engine/adapters/redis/redis_adapter.py") in result
        assert Path("app/engine/adapters/router_client/http_client.py") in result
        assert "Any" in result[Path("app/engine/adapters/redis/redis_adapter.py")]

    def test_detect_missing_imports_ignores_other_errors(self) -> None:
        """Should only detect name-defined errors for imports."""
        mypy_output = dedent("""
            app/engine/bus.py:342: error: No return value expected  [return-value]
            app/engine/core/security.py:123: error: Name "Any" is not defined  [name-defined]
            app/engine/bus.py:407: error: Unexpected keyword argument "data" for "BaseEvent"  [call-arg]
        """).strip()

        from app.engine.tools.import_fixer import detect_missing_imports

        result = detect_missing_imports(mypy_output)

        assert len(result) == 1
        assert Path("app/engine/core/security.py") in result


class TestAddMissingImports:
    """Test adding missing imports to files."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file for testing."""
        return tmp_path / "test_file.py"

    def test_add_missing_imports_to_empty_file(self, temp_file: Path) -> None:
        """Should add typing import to new file."""
        temp_file.write_text("")

        from app.engine.tools.import_fixer import add_missing_imports

        modified = add_missing_imports(temp_file, {"Any"})

        assert modified is True
        content = temp_file.read_text()
        assert "from typing import Any" in content

    def test_add_missing_imports_merges_with_existing(self, temp_file: Path) -> None:
        """Should extend existing typing imports."""
        temp_file.write_text(dedent("""
            from typing import Optional, List

            def process(data: dict[str, Any]) -> List[str]:
                pass
        """).strip())

        from app.engine.tools.import_fixer import add_missing_imports

        modified = add_missing_imports(temp_file, {"Any"})

        assert modified is True
        content = temp_file.read_text()
        assert "from typing import Any, List, Optional" in content
        assert content.count("from typing import") == 1  # No duplicate imports

    def test_add_missing_imports_preserves_formatting(self, temp_file: Path) -> None:
        """Should maintain code style when adding imports."""
        original = dedent('''
            """Module docstring."""

            from dataclasses import dataclass


            @dataclass
            class Config:
                data: dict[str, Any]
        ''').strip()
        temp_file.write_text(original)

        from app.engine.tools.import_fixer import add_missing_imports

        modified = add_missing_imports(temp_file, {"Any"})

        assert modified is True
        content = temp_file.read_text()
        assert '"""Module docstring."""' in content
        assert "from typing import Any" in content
        assert "@dataclass" in content
        # Should preserve double newline before class
        assert "\n\n\n@dataclass" in content or "\n\n@dataclass" in content

    def test_add_missing_imports_handles_multiple_types(self, temp_file: Path) -> None:
        """Should add multiple missing types in one go."""
        temp_file.write_text("def func(): pass")

        from app.engine.tools.import_fixer import add_missing_imports

        modified = add_missing_imports(temp_file, {"Any", "Callable", "Optional"})

        assert modified is True
        content = temp_file.read_text()
        assert "from typing import Any, Callable, Optional" in content

    def test_add_missing_imports_skips_already_imported(self, temp_file: Path) -> None:
        """Should not add types that are already imported."""
        temp_file.write_text("from typing import Any, Optional\n\ndef func(): pass")

        from app.engine.tools.import_fixer import add_missing_imports

        modified = add_missing_imports(temp_file, {"Any"})

        assert modified is False  # No changes needed
        content = temp_file.read_text()
        assert content.count("Any") == 1  # Still just one

    def test_add_missing_imports_handles_future_annotations(self, temp_file: Path) -> None:
        """Should add imports after __future__ imports."""
        temp_file.write_text(dedent("""
            from __future__ import annotations

            def func(data: dict[str, Any]) -> None:
                pass
        """).strip())

        from app.engine.tools.import_fixer import add_missing_imports

        modified = add_missing_imports(temp_file, {"Any"})

        assert modified is True
        content = temp_file.read_text()
        lines = content.split('\n')
        future_idx = next(i for i, line in enumerate(lines) if "__future__" in line)
        typing_idx = next(i for i, line in enumerate(lines) if "from typing import" in line)
        assert typing_idx > future_idx  # typing import comes after __future__


class TestFixAllImportErrors:
    """Test the full import fixing workflow."""

    def test_fix_all_import_errors_reduces_count(self, tmp_path: Path) -> None:
        """Should reduce mypy error count after fixing imports."""
        # This is more of an integration test
        pytest.skip("Integration test - requires full mypy setup")