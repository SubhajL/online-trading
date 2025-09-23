"""Tests for return None fixer."""

import pytest
from app.engine.tools.return_none_fixer import ReturnNoneFixer
from typing import Any




def test_fix_hash_method_return_type():
    """Test fixing __hash__ method that returns None."""
    content = '''class Metric:
    def __hash__(self) -> None:
        return hash((self.name, self.labels))'''

    expected = '''class Metric:
    def __hash__(self) -> int:
        return hash((self.name, self.labels))'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_remove_return_from_none_function():
    """Test removing return statement from function with -> None."""
    content = '''def process_data(data: dict) -> None:
        print(data)
        return True'''

    expected = '''def process_data(data: dict) -> None:
        print(data)'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_fix_return_with_expression():
    """Test removing return with expression from None function."""
    content = '''def update_cache(key: str, value: Any) -> None:
        cache[key] = value
        return cache[key]'''

    expected = '''def update_cache(key: str, value: Any) -> None:
        cache[key] = value'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_preserve_empty_return():
    """Test that empty return statements are preserved."""
    content = '''def early_exit(x: int) -> None:
        if x < 0:
            return
        print(x)'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == content


def test_fix_async_function_with_return():
    """Test fixing async function with incorrect return."""
    content = '''async def async_process() -> None:
        await something()
        return "done"'''

    expected = '''async def async_process() -> None:
        await something()'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_fix_method_in_class():
    """Test fixing method inside a class."""
    content = '''class MyClass:
    def process(self, data: str) -> None:
        self.data = data
        return self.data

    def valid_method(self) -> str:
        return self.data'''

    expected = '''class MyClass:
    def process(self, data: str) -> None:
        self.data = data

    def valid_method(self) -> str:
        return self.data'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_fix_multiple_returns():
    """Test fixing function with multiple return statements."""
    content = '''def complex_function(x: int) -> None:
        if x > 0:
            print("positive")
            return True
        else:
            print("negative")
            return False'''

    expected = '''def complex_function(x: int) -> None:
        if x > 0:
            print("positive")
        else:
            print("negative")'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_handle_empty_content():
    """Test handling empty content."""
    assert ReturnNoneFixer.fix_return_none_errors("") == ""


def test_fix_init_method():
    """Test that __init__ methods with returns are fixed."""
    content = '''class MyClass:
    def __init__(self, value: int) -> None:
        self.value = value
        return self'''

    expected = '''class MyClass:
    def __init__(self, value: int) -> None:
        self.value = value'''

    result = ReturnNoneFixer.fix_return_none_errors(content)
    assert result == expected


def test_fix_file_integration():
    """Test fixing a file with return None errors."""
    import tempfile
    import os

    content = '''class Test:
    def __hash__(self) -> None:
        return hash(self.id)

    def process(self) -> None:
        print("processing")
        return True'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Fix the file
        ReturnNoneFixer.fix_file(temp_path)

        # Read and verify
        with open(temp_path, 'r') as f:
            result = f.read()

        expected = '''class Test:
    def __hash__(self) -> int:
        return hash(self.id)

    def process(self) -> None:
        print("processing")'''

        assert result == expected
    finally:
        os.unlink(temp_path)