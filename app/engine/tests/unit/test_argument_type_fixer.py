"""
Test suite for argument type annotation fixer

Tests the detection and fixing of missing argument type annotations
"""

import pytest
from app.engine.tools.argument_type_fixer import (
    detect_missing_argument_types,
    infer_argument_type,
    add_argument_type_annotations,
    fix_argument_type_annotations
)


class TestDetectMissingArgumentTypes:
    """Tests for detecting functions with missing argument type annotations"""

    def test_detect_function_missing_all_argument_types(self):
        """Should detect functions missing all argument type annotations"""
        code = '''
def calculate_total(a, b):
    return a + b

async def fetch_data(url):
    return await client.get(url)
'''
        missing = detect_missing_argument_types(code)
        assert len(missing) == 2
        assert missing[0]['name'] == 'calculate_total'
        assert missing[0]['line'] == 1
        assert missing[0]['missing_args'] == ['a', 'b']
        assert missing[1]['name'] == 'fetch_data'
        assert missing[1]['missing_args'] == ['url']

    def test_detect_function_missing_some_argument_types(self):
        """Should detect functions with partially annotated arguments"""
        code = '''
def process_data(data: dict, format, output_file):
    formatted = convert(data, format)
    save(formatted, output_file)
'''
        missing = detect_missing_argument_types(code)
        assert len(missing) == 1
        assert missing[0]['name'] == 'process_data'
        assert missing[0]['missing_args'] == ['format', 'output_file']

    def test_ignore_functions_with_all_types(self):
        """Should ignore functions that have all argument types"""
        code = '''
def calculate_total(a: int, b: int) -> int:
    return a + b

async def fetch_data(url: str) -> dict:
    return await client.get(url)
'''
        missing = detect_missing_argument_types(code)
        assert len(missing) == 0

    def test_handle_self_in_class_methods(self):
        """Should ignore 'self' parameter in class methods"""
        code = '''
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, x: int, y):
        return x * y
'''
        missing = detect_missing_argument_types(code)
        assert len(missing) == 2
        assert missing[0]['name'] == 'add'
        assert missing[0]['missing_args'] == ['a', 'b']
        assert 'self' not in missing[0]['missing_args']
        assert missing[1]['name'] == 'multiply'
        assert missing[1]['missing_args'] == ['y']

    def test_handle_cls_in_class_methods(self):
        """Should ignore 'cls' parameter in class methods"""
        code = '''
class Factory:
    @classmethod
    def create(cls, config):
        return cls(config)
'''
        missing = detect_missing_argument_types(code)
        assert len(missing) == 1
        assert missing[0]['missing_args'] == ['config']
        assert 'cls' not in missing[0]['missing_args']

    def test_handle_args_kwargs(self):
        """Should handle *args and **kwargs"""
        code = '''
def flexible_function(name, *args, **kwargs):
    print(f"Name: {name}")
    process_args(args)
    process_kwargs(kwargs)
'''
        missing = detect_missing_argument_types(code)
        assert len(missing) == 1
        assert missing[0]['missing_args'] == ['name']
        # *args and **kwargs should be detected separately
        assert missing[0]['has_args'] is True
        assert missing[0]['has_kwargs'] is True


class TestInferArgumentType:
    """Tests for inferring argument types from usage"""

    def test_infer_from_string_methods(self):
        """Should infer str type from string method calls"""
        code = '''
def process_text(text):
    return text.upper().strip()
'''
        arg_type = infer_argument_type(code, 'process_text', 'text')
        assert arg_type == 'str'

    def test_infer_from_numeric_operations(self):
        """Should infer numeric types from arithmetic operations"""
        code = '''
def calculate(x, y):
    return x + y * 2
'''
        # For now, infer as Any for numeric operations
        arg_type = infer_argument_type(code, 'calculate', 'x')
        assert arg_type == 'Any'

    def test_infer_from_list_operations(self):
        """Should infer list type from list operations"""
        code = '''
def process_items(items):
    items.append("new")
    return len(items)
'''
        arg_type = infer_argument_type(code, 'process_items', 'items')
        assert arg_type == 'list[Any]'

    def test_infer_from_dict_operations(self):
        """Should infer dict type from dict operations"""
        code = '''
def update_config(config):
    config["debug"] = True
    return config.get("version", "1.0")
'''
        arg_type = infer_argument_type(code, 'update_config', 'config')
        assert arg_type == 'dict[str, Any]'

    def test_infer_from_function_calls(self):
        """Should infer Any when used in function calls"""
        code = '''
def wrapper(func):
    return func()
'''
        arg_type = infer_argument_type(code, 'wrapper', 'func')
        assert arg_type == 'Callable[[], Any]'

    def test_cannot_infer_type(self):
        """Should return Any when type cannot be inferred"""
        code = '''
def mystery_function(x):
    if condition:
        return x
    else:
        return None
'''
        arg_type = infer_argument_type(code, 'mystery_function', 'x')
        assert arg_type == 'Any'


class TestAddArgumentTypeAnnotations:
    """Tests for adding argument type annotations"""

    def test_add_types_to_simple_function(self):
        """Should add type annotations to simple function"""
        code = '''
def add(a, b):
    return a + b
'''
        result = add_argument_type_annotations(code)
        assert 'def add(a: Any, b: Any)' in result
        assert 'from typing import Any' in result

    def test_preserve_existing_types(self):
        """Should preserve existing type annotations"""
        code = '''
def process(data: dict, format):
    return convert(data, format)
'''
        result = add_argument_type_annotations(code)
        assert 'def process(data: dict, format: Any)' in result

    def test_handle_multiline_signatures(self):
        """Should handle functions with multiline signatures"""
        code = '''
def complex_function(
    first_param,
    second_param: int,
    third_param
):
    return first_param + second_param + third_param
'''
        result = add_argument_type_annotations(code)
        assert 'first_param: Any' in result
        assert 'second_param: int,' in result  # Preserve existing
        assert 'third_param: Any' in result

    def test_add_types_to_class_methods(self):
        """Should add types to class methods excluding self"""
        code = '''
class MyClass:
    def __init__(self, value):
        self.value = value

    def process(self, data, options):
        return self.value + data
'''
        result = add_argument_type_annotations(code)
        assert 'def __init__(self, value: Any)' in result
        assert 'def process(self, data: Any, options: Any)' in result

    def test_handle_args_kwargs(self):
        """Should add types to *args and **kwargs"""
        code = '''
def flexible(name, *args, **kwargs):
    print(name, args, kwargs)
'''
        result = add_argument_type_annotations(code)
        assert 'def flexible(name: Any, *args: Any, **kwargs: Any)' in result

    def test_infer_string_type(self):
        """Should infer string type from usage"""
        code = '''
def upper_case(text):
    return text.upper()
'''
        result = add_argument_type_annotations(code)
        assert 'def upper_case(text: str)' in result

    def test_handle_async_functions(self):
        """Should handle async function arguments"""
        code = '''
async def fetch(url, timeout):
    return await client.get(url, timeout=timeout)
'''
        result = add_argument_type_annotations(code)
        assert 'async def fetch(url: Any, timeout: Any)' in result


class TestFixArgumentTypeAnnotations:
    """Tests for the main fix function"""

    def test_fix_multiple_functions(self):
        """Should fix argument types in multiple functions"""
        code = '''
def add(x, y):
    return x + y

def greet(name):
    return f"Hello, {name}!"

class Calculator:
    def multiply(self, a, b):
        return a * b
'''
        result = fix_argument_type_annotations(code)
        assert 'def add(x: Any, y: Any)' in result
        assert 'def greet(name: str)' in result
        assert 'def multiply(self, a: Any, b: Any)' in result
        assert 'from typing import Any' in result

    def test_add_multiple_typing_imports(self):
        """Should add necessary typing imports"""
        code = '''
def process_list(items):
    items.append("test")

def handle_callback(func):
    return func()
'''
        result = fix_argument_type_annotations(code)
        assert 'from typing import' in result
        assert any(imp in result for imp in ['Any', 'Callable', 'list'])

    def test_preserve_module_structure(self):
        """Should preserve docstrings and imports"""
        code = '''
"""Module docstring"""

import os
from pathlib import Path

def process_file(filename):
    """Process a file."""
    return Path(filename).read_text()
'''
        result = fix_argument_type_annotations(code)
        assert '"""Module docstring"""' in result
        assert 'import os' in result
        assert 'from pathlib import Path' in result
        assert '"""Process a file."""' in result