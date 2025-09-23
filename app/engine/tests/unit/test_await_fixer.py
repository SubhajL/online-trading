"""Tests for await compatibility fixer."""

import pytest
from app.engine.tools.await_fixer import AwaitFixer


class TestAwaitFixer:
    """Tests for fixing await operations on potentially non-awaitable values."""

    def test_fix_union_await_with_conditional(self) -> None:
        """Test fixing await on Awaitable[T] | T union types."""
        content = '''
async def process(self) -> int:
    result = await self._redis.hset(key, field, value)
    return result
'''
        expected = '''
async def process(self) -> int:
    _result = self._redis.hset(key, field, value)
    result = await _result if hasattr(_result, '__await__') else _result
    return result
'''
        result = AwaitFixer.fix_content(content)
        assert result == expected

    def test_preserve_pure_async_await(self) -> None:
        """Test that clean async/await operations are preserved."""
        content = '''
async def fetch_data(self) -> str:
    response = await self._http_client.get("/api/data")
    return response.text
'''
        result = AwaitFixer.fix_content(content)
        assert result == content

    def test_fix_redis_specific_pattern(self) -> None:
        """Test fixing Redis operations that return Awaitable[T] | T."""
        content = '''
async def cache_value(self, key: str, value: str) -> bool:
    result = await self._redis.set(key, value)
    return bool(result)
'''
        expected = '''
async def cache_value(self, key: str, value: str) -> bool:
    _result = self._redis.set(key, value)
    result = await _result if hasattr(_result, '__await__') else _result
    return bool(result)
'''
        result = AwaitFixer.fix_content(content)
        assert result == expected

    def test_fix_multiple_await_in_function(self) -> None:
        """Test fixing multiple await operations in the same function."""
        content = '''
async def update_cache(self, data: dict) -> None:
    await self._redis.hset("hash1", "field1", "value1")
    await self._redis.expire("hash1", 3600)
    return None
'''
        expected = '''
async def update_cache(self, data: dict) -> None:
    _result = self._redis.hset("hash1", "field1", "value1")
    await _result if hasattr(_result, '__await__') else _result
    _result2 = self._redis.expire("hash1", 3600)
    await _result2 if hasattr(_result2, '__await__') else _result2
    return None
'''
        result = AwaitFixer.fix_content(content)
        assert result == expected

    def test_handle_await_in_complex_expression(self) -> None:
        """Test handling await in complex expressions."""
        content = '''
async def complex_operation(self) -> int:
    count = len(await self._redis.keys("prefix:*"))
    return count
'''
        expected = '''
async def complex_operation(self) -> int:
    _result = self._redis.keys("prefix:*")
    _awaited = await _result if hasattr(_result, '__await__') else _result
    count = len(_awaited)
    return count
'''
        result = AwaitFixer.fix_content(content)
        assert result == expected

    def test_fix_await_with_assignment(self) -> None:
        """Test fixing await with direct assignment."""
        content = '''
async def get_value(self, key: str) -> str | None:
    value = await self._redis.get(key)
    return value.decode() if value else None
'''
        expected = '''
async def get_value(self, key: str) -> str | None:
    _result = self._redis.get(key)
    value = await _result if hasattr(_result, '__await__') else _result
    return value.decode() if value else None
'''
        result = AwaitFixer.fix_content(content)
        assert result == expected

    def test_skip_non_redis_await(self) -> None:
        """Test that non-Redis awaits are not modified."""
        content = '''
async def http_request(self) -> dict:
    async with self._session.get(url) as response:
        data = await response.json()
    return data
'''
        result = AwaitFixer.fix_content(content)
        assert result == content

    def test_handle_await_without_assignment(self) -> None:
        """Test fixing standalone await expressions."""
        content = '''
async def delete_key(self, key: str) -> None:
    await self._redis.delete(key)
'''
        expected = '''
async def delete_key(self, key: str) -> None:
    _result = self._redis.delete(key)
    await _result if hasattr(_result, '__await__') else _result
'''
        result = AwaitFixer.fix_content(content)
        assert result == expected

    def test_empty_content_returns_empty(self) -> None:
        """Test that empty content returns empty string."""
        assert AwaitFixer.fix_content("") == ""
        assert AwaitFixer.fix_content("   \n  ") == "   \n  "

    def test_fix_file_integration(self) -> None:
        """Test fixing a file with await compatibility issues."""
        import tempfile
        import os

        content = '''
async def redis_operations(self) -> bool:
    success = await self._redis.set("test_key", "test_value")
    ttl = await self._redis.ttl("test_key")
    return success and ttl > 0
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            AwaitFixer.fix_file(temp_path)

            with open(temp_path, 'r') as f:
                result = f.read()

            assert 'hasattr' in result
            assert '__await__' in result
            assert '_result' in result
        finally:
            os.unlink(temp_path)