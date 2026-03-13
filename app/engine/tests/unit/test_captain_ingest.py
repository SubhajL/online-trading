"""
Unit tests for Captain Trading Telegram ingestion helpers.
"""

from decimal import Decimal

import pytest

pytest.importorskip("pytesseract", reason="pytesseract is not installed")
pytest.importorskip("telethon", reason="telethon is not installed")

from app.engine.telegram_validator.captain_image_levels import TradeLevels
from app.engine.telegram_validator.captain_ingest import build_external_signal_fields


def test_build_external_signal_fields_trade_uses_text_and_ocr_levels() -> None:
    text = """
🖼 ⚠️ตรวจพบสัญญาณเข้าเทรด⚠️

🚨SMC Hybrid Signal🚨
_______________________

📈สัญญาณ : SELL
🏅สินทรัพย์ : BTCUSD
⏱️กรอบเวลา : M30
"""

    levels = TradeLevels(
        entry=Decimal("4499.70"),
        stop_loss=Decimal("4525.87"),
        take_profits=[Decimal("4482.73"), Decimal("4430.57")],
        raw_ocr_text="Entry: 4499.70",
    )

    fields = build_external_signal_fields(text=text, ocr_levels=levels)

    assert fields["kind"] == "TRADE_SIGNAL"
    assert fields["strategy"] == "SMC_HYBRID"
    assert fields["symbol"] == "BTCUSDT"
    assert fields["timeframe"] == "30m"
    assert fields["direction"] == "SELL"
    assert fields["entry_price"] == "4499.70"
    assert fields["stop_loss"] == "4525.87"
    assert fields["take_profits"] == ["4482.73", "4430.57"]
    assert fields["parse_sources"] == ["text", "image"]
    assert fields["ocr_raw_text"] == "Entry: 4499.70"


def test_build_external_signal_fields_news_keeps_kind_without_trade_fields() -> None:
    text = """
⚠️ แจ้งเตือนข่าวกล่องแดงในอีก 30 minutes ⚠️

🚨 Forex Factory Calendar 🚨
📈 ข่าว: Unemployment Claims
"""

    fields = build_external_signal_fields(text=text, ocr_levels=None)

    assert fields["kind"] == "NEWS_ALERT"
    assert fields["strategy"] == "UNKNOWN"
    assert fields["symbol"] is None
    assert fields["direction"] is None
