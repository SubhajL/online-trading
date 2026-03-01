"""
Unit tests for parsing Captain Trading Telegram messages (Thai + mixed content).
"""

import pytest

from app.engine.telegram_validator.captain_parse import (
    classify_captain_message,
    normalize_external_symbol,
    normalize_external_timeframe,
    parse_captain_trade_signal_from_text,
)


def test_classify_captain_news_alert() -> None:
    kind, strategy = classify_captain_message(
        "⚠️ แจ้งเตือนข่าวกล่องแดงในอีก 30 minutes ⚠️\n\n🚨 Forex Factory Calendar 🚨",
    )
    assert kind == "NEWS_ALERT"
    assert strategy == "UNKNOWN"


def test_classify_captain_quasimodo_trade_signal() -> None:
    kind, strategy = classify_captain_message("🚨Captain Quasimodo🚨\n📈สัญญาณ : SELL 🔻")
    assert kind == "TRADE_SIGNAL"
    assert strategy == "QUASIMODO"


def test_normalize_external_timeframe_maps_to_engine_values() -> None:
    assert normalize_external_timeframe("M30") == "30m"
    assert normalize_external_timeframe("H1") == "1h"
    assert normalize_external_timeframe("H4") == "4h"


@pytest.mark.parametrize(
    ("external", "expected"),
    [
        ("BTCUSD", "BTCUSDT"),
        ("EURUSD", "EURUSD"),
        ("GBPUSD", "GBPUSD"),
        ("XAUUSD", "XAUUSD"),
        ("USDJPY", "USDJPY"),
    ],
)
def test_normalize_external_symbol(external: str, expected: str) -> None:
    assert normalize_external_symbol(external) == expected


def test_parse_captain_trade_signal_from_thai_text() -> None:
    text = """
🖼 ⚠️ตรวจพบสัญญาณเข้าเทรด⚠️

🚨SMC Hybrid Signal🚨
_______________________

📈สัญญาณ : SELL
🏅สินทรัพย์ : GBPUSD
⏱️กรอบเวลา : M30
"""

    signal = parse_captain_trade_signal_from_text(text)
    assert signal is not None
    assert signal["direction"] == "SELL"
    assert signal["symbol"] == "GBPUSD"
    assert signal["timeframe"] == "30m"

