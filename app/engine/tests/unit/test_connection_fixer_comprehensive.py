"""
Test suite for connection type annotation fixer

Tests the detection and fixing of database connection type annotations
"""

import pytest
from app.engine.tools.connection_fixer import (
    detect_connection_patterns,
    add_connection_type_hints,
    fix_connection_annotations
)


class TestDetectConnectionPatterns:
    """Tests for detecting connection patterns that need type annotations"""

    def test_detect_async_context_manager_with_none_return(self):
        """Should detect async context manager get_connection with wrong return type"""
        code = '''
@asynccontextmanager
async def get_connection(self) -> None:
    async with self._pool.acquire() as connection:
        yield connection
'''
        patterns = detect_connection_patterns(code)
        # Should detect both the async context manager return type and connection variable
        async_cm_patterns = [p for p in patterns if p['type'] == 'async_context_manager']
        assert len(async_cm_patterns) == 1
        assert async_cm_patterns[0]['method'] == 'get_connection'
        assert async_cm_patterns[0]['line'] == 2
        assert async_cm_patterns[0]['current_return'] == 'None'

    def test_detect_missing_connection_annotation(self):
        """Should detect missing type annotation for connection variable"""
        code = '''
async def execute_query(self, query: str):
    async with self.pool.acquire() as conn:
        return await conn.fetch(query)
'''
        patterns = detect_connection_patterns(code)
        assert len(patterns) == 1
        assert patterns[0]['type'] == 'connection_variable'
        assert patterns[0]['variable'] == 'conn'
        assert patterns[0]['line'] == 2

    def test_detect_get_connection_missing_annotation(self):
        """Should detect connection = await get_connection() pattern"""
        code = '''
async def save_data(self):
    connection = await self.get_connection()
    await connection.execute("INSERT ...")
'''
        patterns = detect_connection_patterns(code)
        assert len(patterns) == 1
        assert patterns[0]['type'] == 'await_get_connection'
        assert patterns[0]['variable'] == 'connection'
        assert patterns[0]['line'] == 2

    def test_ignore_properly_annotated(self):
        """Should not detect already annotated connections"""
        code = '''
from asyncpg import Connection

async def execute_query(self, query: str):
    conn: Connection = await self.pool.acquire()
    return await conn.fetch(query)
'''
        patterns = detect_connection_patterns(code)
        assert len(patterns) == 0


class TestAddConnectionTypeHints:
    """Tests for adding connection type hints"""

    def test_fix_async_context_manager_return_type(self):
        """Should fix async context manager return type"""
        code = '''from typing import AsyncIterator
import asyncpg

class DBAdapter:
    @asynccontextmanager
    async def get_connection(self) -> None:
        async with self._pool.acquire() as connection:
            yield connection
'''
        result = add_connection_type_hints(code)
        # Check that the return type was fixed
        assert '-> AsyncIterator[asyncpg.Connection]' in result
        # Check that the connection variable got an annotation too
        assert '# connection: asyncpg.Connection' in result

    def test_add_asynciterator_import_if_needed(self):
        """Should add AsyncIterator import if not present"""
        code = '''import asyncpg

@asynccontextmanager
async def get_connection(self) -> None:
    async with self._pool.acquire() as connection:
        yield connection
'''
        result = add_connection_type_hints(code)
        assert 'from typing import AsyncIterator' in result
        assert '-> AsyncIterator[asyncpg.Connection]' in result

    def test_add_connection_variable_annotation(self):
        """Should add type annotation to connection variable"""
        code = '''import asyncpg

async def execute_query(self, query: str):
    async with self.pool.acquire() as conn:
        return await conn.fetch(query)
'''
        expected = '''import asyncpg

async def execute_query(self, query: str):
    async with self.pool.acquire() as conn:  # conn: asyncpg.Connection
        return await conn.fetch(query)
'''
        result = add_connection_type_hints(code)
        assert '# conn: asyncpg.Connection' in result

    def test_add_await_connection_annotation(self):
        """Should add type annotation for await get_connection()"""
        code = '''from asyncpg import Connection

async def save_data(self):
    connection = await self.get_connection()
    await connection.execute("INSERT ...")
'''
        expected = '''from asyncpg import Connection

async def save_data(self):
    connection: Connection = await self.get_connection()
    await connection.execute("INSERT ...")
'''
        result = add_connection_type_hints(code)
        assert 'connection: Connection' in result

    def test_preserve_existing_imports_and_structure(self):
        """Should preserve code structure when adding annotations"""
        code = '''"""Module docstring"""

from typing import List, Dict
import asyncpg
from contextlib import asynccontextmanager

class DBAdapter:
    """Class docstring"""

    @asynccontextmanager
    async def get_connection(self) -> None:
        async with self._pool.acquire() as connection:
            yield connection
'''
        result = add_connection_type_hints(code)
        assert '"""Module docstring"""' in result
        assert 'from typing import List, Dict, AsyncIterator' in result
        assert '"""Class docstring"""' in result
        assert '-> AsyncIterator[asyncpg.Connection]' in result


class TestFixConnectionAnnotations:
    """Tests for the main fix function that processes files"""

    def test_fix_file_with_multiple_patterns(self):
        """Should fix multiple connection patterns in a single file"""
        code = '''import asyncpg
from contextlib import asynccontextmanager

class DBAdapter:
    @asynccontextmanager
    async def get_connection(self) -> None:
        async with self._pool.acquire() as connection:
            yield connection

    async def execute_query(self, query: str):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query)

    async def save_data(self):
        connection = await self.get_connection()
        await connection.execute("INSERT ...")
'''
        result = fix_connection_annotations(code)
        assert 'from typing import AsyncIterator' in result
        assert '-> AsyncIterator[asyncpg.Connection]' in result
        assert '# conn: asyncpg.Connection' in result
        assert 'connection: asyncpg.Connection' in result

    def test_handle_transaction_pattern(self):
        """Should handle transaction context manager patterns"""
        code = '''import asyncpg

async def with_transaction(self):
    async with self.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE ...")
'''
        result = fix_connection_annotations(code)
        assert '# conn: asyncpg.Connection' in result