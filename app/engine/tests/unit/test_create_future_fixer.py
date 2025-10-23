"""Tests for create_future fixer."""

import asyncio
import pytest
from app.engine.tools.create_future_fixer import CreateFutureFixer


def test_fix_create_future_simple():
    loop = asyncio.get_event_loop()
    """Test fixing simple loop.create_future() calls."""
    content = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    future.set_result(42)
    return future'''

    expected = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    future.set_result(42)
    return future'''

    result = CreateFutureFixer.fix_create_future(content)
    assert result == expected


def test_fix_create_future_with_mock():
    """Test fixing create_future in mock scenarios."""
    content = '''import asyncio
from unittest.mock import patch

async def test_something():
    with patch.object(obj, 'method') as mock:
        loop = asyncio.get_event_loop()
        mock.return_value = loop.create_future()
        mock.return_value.set_result({"ok": True})'''

    expected = '''import asyncio
from unittest.mock import patch

async def test_something():
    with patch.object(obj, 'method') as mock:
        loop = asyncio.get_event_loop()
        mock.return_value = loop.create_future()
        mock.return_value.set_result({"ok": True})'''

    result = CreateFutureFixer.fix_create_future(content)
    assert result == expected


def test_fix_multiple_create_futures():
    """Test fixing multiple create_future calls."""
    content = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future1 = loop.create_future()
    future2 = loop.create_future()
    return future1, future2'''

    expected = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future1 = loop.create_future()
    future2 = loop.create_future()
    return future1, future2'''

    result = CreateFutureFixer.fix_create_future(content)
    assert result == expected


def test_preserve_existing_loop_variable():
    """Test that existing loop variables are reused."""
    content = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    # Do something with loop
    future = loop.create_future()
    return future'''

    expected = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    # Do something with loop
    future = loop.create_future()
    return future'''

    result = CreateFutureFixer.fix_create_future(content)
    assert result == expected


def test_fix_nested_function():
    """Test fixing create_future in nested functions."""
    content = '''import asyncio

class TestClass:
    async def test_method(self):
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        future.set_result(True)'''

    expected = '''import asyncio

class TestClass:
    async def test_method(self):
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        future.set_result(True)'''

    result = CreateFutureFixer.fix_create_future(content)
    assert result == expected


def test_no_changes_when_no_create_future():
    """Test that code without create_future is unchanged."""
    content = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    return future'''

    result = CreateFutureFixer.fix_create_future(content)
    assert result == content


def test_fix_file_integration():
    """Test fixing a file with create_future errors."""
    import tempfile
    import os

    content = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    return future'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Fix the file
        CreateFutureFixer.fix_file(temp_path)

        # Read and verify
        with open(temp_path, 'r') as f:
            result = f.read()

        expected = '''import asyncio

async def test():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    return future'''

        assert result == expected
    finally:
        os.unlink(temp_path)


def test_handle_empty_content():
    """Test handling empty content."""
    assert CreateFutureFixer.fix_create_future("") == ""
