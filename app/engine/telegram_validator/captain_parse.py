"""
Captain Trading message parsing utilities.

Captures Captain's Telegram channel content into a canonical format for validation.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from .thai_signal_parser import parse_mixed_thai_english

ExternalAlertKind = Literal["TRADE_SIGNAL", "NEWS_ALERT"]
ExternalStrategyTag = Literal["SMC_HYBRID", "QUASIMODO", "UNKNOWN"]


class CaptainTradeSignal(TypedDict):
    symbol: str
    direction: Literal["BUY", "SELL"]
    timeframe: str
    strategy: ExternalStrategyTag


_FIAT_CODES = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "NZD",
    "CAD",
    "CHF",
}

_COMMODITY_CODES = {"XAU", "XAG"}


def classify_captain_message(text: str) -> tuple[ExternalAlertKind, ExternalStrategyTag]:
    """Classify message as trade signal or news alert, and tag the strategy."""
    upper = text.upper()

    if "FOREX FACTORY" in upper or "CALENDAR" in upper or "แจ้งเตือนข่าว" in text:
        return "NEWS_ALERT", "UNKNOWN"

    if "CAPTAIN QUASIMODO" in upper:
        return "TRADE_SIGNAL", "QUASIMODO"

    if "SMC HYBRID SIGNAL" in upper:
        return "TRADE_SIGNAL", "SMC_HYBRID"

    return "TRADE_SIGNAL", "UNKNOWN"


def normalize_external_timeframe(raw: str) -> str:
    """Normalize Captain timeframe tokens like M30/H1/H4 to engine values."""
    token = raw.strip().upper()
    m = re.fullmatch(r"M(\d+)", token)
    if m:
        return f"{m.group(1)}m"
    h = re.fullmatch(r"H(\d+)", token)
    if h:
        return f"{h.group(1)}h"
    if token in {"D1", "W1"}:
        return token[0].lower() + "1"
    return raw


def normalize_external_symbol(raw: str) -> str:
    """Normalize Captain symbols for our engine (BTCUSD -> BTCUSDT, FX untouched)."""
    symbol = raw.strip().upper()
    if len(symbol) < 6:
        return symbol

    base, quote = symbol[:-3], symbol[-3:]
    if quote != "USD":
        return symbol

    if base in _COMMODITY_CODES:
        return symbol

    if base in _FIAT_CODES:
        return symbol

    # Default for crypto-style symbols that end with USD.
    return f"{base}USDT"


def parse_captain_trade_signal_from_text(text: str) -> CaptainTradeSignal | None:
    """Parse Captain Thai/mixed trade signal messages into a canonical structure."""
    kind, strategy = classify_captain_message(text)
    if kind != "TRADE_SIGNAL":
        return None

    parsed = parse_mixed_thai_english(text)
    if not parsed:
        return None

    return {
        "symbol": normalize_external_symbol(parsed.symbol),
        "direction": "BUY" if parsed.direction.upper() == "BUY" else "SELL",
        "timeframe": normalize_external_timeframe(
            _extract_timeframe_token(parsed.reasoning, text),
        ),
        "strategy": strategy,
    }


def _extract_timeframe_token(reasoning: str, text: str) -> str:
    """Extract timeframe token from either Thai fields or the parsed reasoning."""
    # Prefer explicit Thai field match: "กรอบเวลา : M30"
    match = re.search(r"กรอบเวลา\s*[:：]\s*([A-Za-z0-9]+)", text)
    if match:
        return match.group(1)

    # Fall back to patterns like "H1", "M30" inside reasoning.
    match = re.search(r"\b([MH]\d+)\b", reasoning, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    return "H4"
