"""
Unit tests for extracting entry/SL/TP levels from Captain Trading chart images.
"""

from decimal import Decimal

from app.engine.telegram_validator import captain_image_levels


def test_parse_decimal_repairs_extra_leading_digit() -> None:
    entry = Decimal("4500.00")
    assert captain_image_levels._parse_decimal("24430.57", reference=entry) == Decimal("4430.57")


def test_normalize_ocr_text_fixes_common_confusions() -> None:
    raw = "tp1: 45O0.87\\nS TOP 4525.87"
    normalized = captain_image_levels._normalize_ocr_text(raw)

    assert "TP 1" in normalized
    assert "STOP" in normalized
    assert "4500.87" in normalized


def test_extract_take_profits_dedups_and_preserves_order() -> None:
    text = "TP1: 4482.73 TP2 4430.57 TP1 4482.73"
    normalized = captain_image_levels._normalize_ocr_text(text)
    levels = captain_image_levels._extract_take_profits(normalized, entry=Decimal("4500.00"))
    assert levels == [Decimal("4482.73"), Decimal("4430.57")]
