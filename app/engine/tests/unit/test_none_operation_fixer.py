"""Tests for None operation fixer."""

import pytest
from app.engine.tools.none_operation_fixer import NoneOperationFixer


class TestNoneOperationFixer:
    """Tests for fixing operations that could fail with None values."""

    def test_fix_multiplication_with_none_adds_guard(self) -> None:
        """Test adding None check before multiplication operation."""
        content = '''
def calculate_cost(price: Decimal | None, quantity: Decimal) -> Decimal:
    return price * quantity
'''
        expected = '''
def calculate_cost(price: Decimal | None, quantity: Decimal) -> Decimal:
    if price is None:
        return Decimal(0)
    return price * quantity
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_fix_addition_with_none_adds_guard(self) -> None:
        """Test adding None check before addition operation."""
        content = '''
def add_values(a: float | None, b: float) -> float:
    return a + b
'''
        expected = '''
def add_values(a: float | None, b: float) -> float:
    if a is None:
        return b
    return a + b
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_preserve_already_guarded_operations(self) -> None:
        """Test that operations with existing None checks are preserved."""
        content = '''
def safe_multiply(x: Decimal | None, y: Decimal) -> Decimal:
    if x is None:
        return Decimal(0)
    return x * y
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == content

    def test_fix_chained_attribute_operations(self) -> None:
        """Test fixing operations on potentially None attributes."""
        content = '''
def calculate_fee(order: Order | None) -> Decimal:
    return order.price * order.fee_rate
'''
        expected = '''
def calculate_fee(order: Order | None) -> Decimal:
    if order is None:
        return Decimal(0)
    return order.price * order.fee_rate
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_fix_inline_ternary_operations(self) -> None:
        """Test converting unsafe operations to safe ternary expressions."""
        content = '''
def get_value(x: int | None, multiplier: int) -> int:
    result = x * multiplier
    return result
'''
        expected = '''
def get_value(x: int | None, multiplier: int) -> int:
    result = x * multiplier if x is not None else 0
    return result
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_fix_multiple_none_operations_in_function(self) -> None:
        """Test fixing multiple None operations in the same function."""
        content = '''
def complex_calc(a: Decimal | None, b: Decimal | None, c: Decimal) -> Decimal:
    x = a * c
    y = b + c
    return x + y
'''
        expected = '''
def complex_calc(a: Decimal | None, b: Decimal | None, c: Decimal) -> Decimal:
    x = a * c if a is not None else Decimal(0)
    y = b + c if b is not None else c
    return x + y
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_fix_subtraction_with_none(self) -> None:
        """Test fixing subtraction operations with None."""
        content = '''
def subtract_values(total: Decimal, discount: Decimal | None) -> Decimal:
    return total - discount
'''
        expected = '''
def subtract_values(total: Decimal, discount: Decimal | None) -> Decimal:
    if discount is None:
        return total
    return total - discount
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_fix_division_with_none(self) -> None:
        """Test fixing division operations with None."""
        content = '''
def calculate_rate(total: Decimal, count: int | None) -> Decimal:
    return total / count
'''
        expected = '''
def calculate_rate(total: Decimal, count: int | None) -> Decimal:
    if count is None:
        return Decimal(0)
    return total / count
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_handle_complex_expressions(self) -> None:
        """Test handling complex expressions with multiple operations."""
        content = '''
def calculate_total(base: Decimal | None, tax_rate: Decimal) -> Decimal:
    return (base * tax_rate) + base
'''
        expected = '''
def calculate_total(base: Decimal | None, tax_rate: Decimal) -> Decimal:
    if base is None:
        return Decimal(0)
    return (base * tax_rate) + base
'''
        result = NoneOperationFixer.fix_content(content)
        assert result == expected

    def test_empty_content_returns_empty(self) -> None:
        """Test that empty content returns empty string."""
        assert NoneOperationFixer.fix_content("") == ""
        assert NoneOperationFixer.fix_content("   \n  ") == "   \n  "

    def test_fix_file_integration(self) -> None:
        """Test fixing a file with None operations."""
        import tempfile
        import os

        content = '''
def process_order(order: Order | None) -> Decimal:
    base_cost = order.quantity * order.price
    with_tax = base_cost * Decimal("1.1")
    return with_tax
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            NoneOperationFixer.fix_file(temp_path)

            with open(temp_path, 'r') as f:
                result = f.read()

            # Check that the operation is guarded with ternary
            assert 'if order is not None else' in result
        finally:
            os.unlink(temp_path)