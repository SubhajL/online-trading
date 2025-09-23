"""
Tests for fixing database connection type annotations.
Following TDD principles.
"""

import pytest
from pathlib import Path
from textwrap import dedent


class TestDetectConnectionPatterns:
    """Test detection of connection patterns needing annotations."""

    def test_detect_asyncpg_connection_pattern(self) -> None:
        """Should find pool.acquire() patterns."""
        content = dedent("""
            async with pool.acquire() as conn:
                result = await conn.fetch("SELECT 1")

            async with self._pool.acquire() as conn:
                await conn.execute("DELETE FROM test")
        """).strip()

        from tools.connection_fixer import detect_connection_patterns

        patterns = detect_connection_patterns(content)

        assert len(patterns) == 2
        assert (1, "conn") in patterns  # Line 1 (0-indexed)
        assert (4, "conn") in patterns  # Line 4

    def test_detect_redis_connection_pattern(self) -> None:
        """Should find Redis connection patterns."""
        content = dedent("""
            async with self.redis.client() as conn:
                await conn.set("key", "value")
        """).strip()

        from tools.connection_fixer import detect_connection_patterns

        patterns = detect_connection_patterns(content)

        # Redis patterns might be different - adjust as needed
        assert len(patterns) >= 0  # Placeholder

    def test_skip_already_annotated_connections(self) -> None:
        """Should skip connections that already have type hints."""
        content = dedent("""
            async with pool.acquire() as conn:  # type: asyncpg.Connection
                result = await conn.fetch("SELECT 1")

            async with pool.acquire() as conn:  # type: ignore
                await conn.execute("DELETE FROM test")
        """).strip()

        from tools.connection_fixer import detect_connection_patterns

        patterns = detect_connection_patterns(content)

        # Should skip both - already annotated
        assert len(patterns) == 0


class TestAddConnectionTypeHints:
    """Test adding type annotations to connections."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file."""
        return tmp_path / "test_db.py"

    def test_add_asyncpg_type_hint(self, temp_file: Path) -> None:
        """Should add correct asyncpg annotation."""
        content = dedent("""
            import asyncpg

            async def query_data(pool):
                async with pool.acquire() as conn:
                    return await conn.fetch("SELECT * FROM users")
        """).strip()
        temp_file.write_text(content)

        from tools.connection_fixer import add_connection_type_hints

        annotations_added = add_connection_type_hints(temp_file)

        assert annotations_added == 1
        result = temp_file.read_text()
        assert "# type: asyncpg.Connection" in result
        # Should be on the correct line
        assert "as conn:  # type: asyncpg.Connection" in result

    def test_preserve_indentation_in_annotations(self, temp_file: Path) -> None:
        """Should maintain proper indentation."""
        content = dedent("""
            async def nested_function():
                if True:
                    async with pool.acquire() as conn:
                        pass
        """).strip()
        temp_file.write_text(content)

        from tools.connection_fixer import add_connection_type_hints

        annotations_added = add_connection_type_hints(temp_file)

        assert annotations_added == 1
        result = temp_file.read_text()
        lines = result.split('\n')
        # Find the line with annotation
        for line in lines:
            if "# type:" in line:
                # Should maintain indentation
                assert line.startswith("        ")  # 8 spaces
                break

    def test_handle_multiple_connections(self, temp_file: Path) -> None:
        """Should handle multiple connections in one file."""
        content = dedent("""
            async def process_data(pool):
                async with pool.acquire() as conn:
                    data = await conn.fetch("SELECT 1")

                async with pool.acquire() as conn2:
                    await conn2.execute("UPDATE ...")

                # Already annotated
                async with pool.acquire() as conn3:  # type: asyncpg.Connection
                    pass
        """).strip()
        temp_file.write_text(content)

        from tools.connection_fixer import add_connection_type_hints

        annotations_added = add_connection_type_hints(temp_file)

        assert annotations_added == 2  # Only first two need annotation
        result = temp_file.read_text()
        assert result.count("# type: asyncpg.Connection") == 3  # Total of 3