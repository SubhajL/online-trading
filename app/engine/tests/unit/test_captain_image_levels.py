"""
Unit tests for extracting entry/SL/TP levels from Captain Trading chart images.
"""

from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("pytesseract")

from app.engine.telegram_validator.captain_image_levels import extract_trade_levels_from_image_bytes


def test_extract_trade_levels_from_sample_image() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    image_path = repo_root / "tests" / "UX" / "Screenshot 2568-12-26 at 16.01.08.png"

    image_bytes = image_path.read_bytes()
    result = extract_trade_levels_from_image_bytes(image_bytes)

    assert result is not None
    assert result.entry == Decimal("4499.70")
    assert result.stop_loss == Decimal("4525.87")
    assert result.take_profits == [Decimal("4482.73"), Decimal("4430.57")]
