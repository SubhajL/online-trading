"""Tests for undefined name fixer."""

import pytest
from app.engine.tools.undefined_name_fixer import UndefinedNameFixer


def test_fix_missing_any_import():
    """Test adding missing Any import."""
    content = '''from typing import Dict

def process(data: Any) -> Any:
    return data'''

    expected = '''from typing import Any, Dict

def process(data: Any) -> Any:
    return data'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_fix_missing_decimal_import():
    """Test adding missing Decimal import."""
    content = '''def calculate_price(amount: float) -> Decimal:
    return Decimal(str(amount))'''

    expected = '''from decimal import Decimal


def calculate_price(amount: float) -> Decimal:
    return Decimal(str(amount))'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_fix_both_any_and_decimal():
    """Test adding both Any and Decimal imports."""
    content = '''from typing import Dict

def process(data: Any) -> Decimal:
    return Decimal("100.50")'''

    expected = '''from typing import Any, Dict
from decimal import Decimal

def process(data: Any) -> Decimal:
    return Decimal("100.50")'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_add_any_to_existing_typing_import():
    """Test adding Any to existing typing import."""
    content = '''from typing import Dict, List

def get_items() -> List[Any]:
    return []'''

    expected = '''from typing import Any, Dict, List

def get_items() -> List[Any]:
    return []'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_preserve_existing_imports():
    """Test that existing imports are preserved."""
    content = '''from decimal import Decimal
from typing import Any, Dict

def calculate(value: Any) -> Decimal:
    return Decimal(value)'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == content


def test_fix_multiple_any_usages():
    """Test fixing file with multiple Any usages."""
    content = '''def func1(x: Any) -> Any:
    pass

def func2(y: Any, z: dict[str, Any]) -> list[Any]:
    pass'''

    expected = '''from typing import Any


def func1(x: Any) -> Any:
    pass

def func2(y: Any, z: dict[str, Any]) -> list[Any]:
    pass'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_fix_file_integration():
    """Test fixing a file with undefined names."""
    import tempfile
    import os

    content = '''from typing import Dict

def calculate(value: Any) -> Decimal:
    return Decimal(str(value))'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Fix the file
        UndefinedNameFixer.fix_file(temp_path)

        # Read and verify
        with open(temp_path, 'r') as f:
            result = f.read()

        expected = '''from typing import Any, Dict
from decimal import Decimal

def calculate(value: Any) -> Decimal:
    return Decimal(str(value))'''

        assert result == expected
    finally:
        os.unlink(temp_path)


def test_handle_empty_content():
    """Test handling empty content."""
    assert UndefinedNameFixer.fix_undefined_names("") == ""


def test_dont_duplicate_imports():
    """Test that imports aren't duplicated if already present."""
    content = '''from typing import Any, Dict
from decimal import Decimal

def func(x: Any) -> Decimal:
    return Decimal(x)'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == content


def test_fix_with_existing_decimal_import_different_format():
    """Test fixing when Decimal is imported differently."""
    content = '''import decimal

def calculate() -> Decimal:
    return Decimal("100")'''

    expected = '''import decimal
from decimal import Decimal



def calculate() -> Decimal:
    return Decimal("100")'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_fix_any_in_dict_generics():
    """Test fixing undefined Any in dict generic types."""
    content = '''class MyClass:
    def __init__(self):
        self.trades: list[dict[Any, Any]] = []
        self.positions: dict[str, dict[Any, Any]] = {}'''

    expected = '''from typing import Any


class MyClass:
    def __init__(self):
        self.trades: list[dict[Any, Any]] = []
        self.positions: dict[str, dict[Any, Any]] = {}'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected


def test_fix_any_in_union_types():
    """Test fixing undefined Any in union types."""
    content = '''def process(data: str | Any | None) -> dict[Any, Any] | None:
    return None'''

    expected = '''from typing import Any


def process(data: str | Any | None) -> dict[Any, Any] | None:
    return None'''

    result = UndefinedNameFixer.fix_undefined_names(content)
    assert result == expected