"""Tests for generic isinstance fixer."""

import pytest
from app.engine.tools.generic_isinstance_fixer import GenericIsinstanceFixer


class TestGenericIsinstanceFixer:
    """Tests for fixing parameterized generic isinstance checks."""

    def test_fix_dict_isinstance_converts_to_simple_dict(self) -> None:
        """Test that isinstance(x, dict[str, Any]) becomes isinstance(x, dict)."""
        content = '''
def process_data(data: Any) -> bool:
    if isinstance(data, dict[str, Any]):
        return True
    return False
'''
        expected = '''
def process_data(data: Any) -> bool:
    if isinstance(data, dict):
        return True
    return False
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_fix_list_isinstance_converts_to_simple_list(self) -> None:
        """Test that isinstance(x, list[str]) becomes isinstance(x, list)."""
        content = '''
def validate_strings(items: Any) -> bool:
    return isinstance(items, list[str])
'''
        expected = '''
def validate_strings(items: Any) -> bool:
    return isinstance(items, list)
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_preserve_non_generic_isinstance(self) -> None:
        """Test that simple isinstance checks are preserved unchanged."""
        content = '''
def check_type(obj: Any) -> str:
    if isinstance(obj, dict):
        return "dict"
    elif isinstance(obj, list):
        return "list"
    return "other"
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == content

    def test_fix_union_isinstance_with_none(self) -> None:
        """Test handling of Union types with None in isinstance."""
        content = '''
def process(data: Any) -> bool:
    if isinstance(data, dict[str, Any] | None):
        return True
    return False
'''
        expected = '''
def process(data: Any) -> bool:
    if isinstance(data, dict) or data is None:
        return True
    return False
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_fix_nested_generic_isinstance(self) -> None:
        """Test fixing nested generic types like list[dict[str, Any]]."""
        content = '''
def validate_complex(obj: Any) -> bool:
    return isinstance(obj, list[dict[str, Any]])
'''
        expected = '''
def validate_complex(obj: Any) -> bool:
    return isinstance(obj, list)
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_fix_multiple_isinstance_in_one_line(self) -> None:
        """Test fixing multiple isinstance checks in the same condition."""
        content = '''
def check_types(a: Any, b: Any) -> bool:
    return isinstance(a, list[str]) and isinstance(b, dict[str, int])
'''
        expected = '''
def check_types(a: Any, b: Any) -> bool:
    return isinstance(a, list) and isinstance(b, dict)
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_handle_multiline_isinstance(self) -> None:
        """Test handling isinstance that spans multiple lines."""
        content = '''
def validate(data: Any) -> bool:
    return isinstance(
        data,
        dict[str, Any]
    )
'''
        expected = '''
def validate(data: Any) -> bool:
    return isinstance(
        data,
        dict
    )
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_fix_isinstance_with_type_alias(self) -> None:
        """Test fixing isinstance with type aliases."""
        content = '''
from typing import Any

JsonDict = dict[str, Any]

def is_json(data: Any) -> bool:
    return isinstance(data, dict[str, Any])
'''
        expected = '''
from typing import Any

JsonDict = dict[str, Any]

def is_json(data: Any) -> bool:
    return isinstance(data, dict)
'''
        result = GenericIsinstanceFixer.fix_content(content)
        assert result == expected

    def test_empty_content_returns_empty(self) -> None:
        """Test that empty content returns empty string."""
        assert GenericIsinstanceFixer.fix_content("") == ""
        assert GenericIsinstanceFixer.fix_content("   \n  ") == "   \n  "

    def test_fix_file_integration(self) -> None:
        """Test fixing a file with generic isinstance checks."""
        import tempfile
        import os

        content = '''
def check_response(resp: Any) -> str:
    if isinstance(resp, dict[str, Any]):
        return "json"
    elif isinstance(resp, list[dict[str, Any]]):
        return "json_array"
    return "unknown"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            GenericIsinstanceFixer.fix_file(temp_path)

            with open(temp_path, 'r') as f:
                result = f.read()

            assert 'isinstance(resp, dict)' in result
            assert 'isinstance(resp, list)' in result
            assert 'dict[str, Any]' not in result.split('isinstance')[-1]
        finally:
            os.unlink(temp_path)