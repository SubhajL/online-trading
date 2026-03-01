"""
Captain Trading Telegram ingestion helpers.

This module converts raw Telegram message content (text + optional OCR) into the
fields persisted for external signal benchmarking.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from .captain_image_levels import TradeLevels
from .captain_parse import (
    ExternalAlertKind,
    ExternalStrategyTag,
    classify_captain_message,
    parse_captain_trade_signal_from_text,
)


class ExternalSignalFields(TypedDict):
    kind: ExternalAlertKind
    strategy: ExternalStrategyTag
    symbol: str | None
    timeframe: str | None
    direction: Literal["BUY", "SELL"] | None
    entry_price: str | None
    stop_loss: str | None
    take_profits: list[str] | None
    parse_confidence: float | None
    parse_sources: list[str]
    ocr_raw_text: str | None


def build_external_signal_fields(
    *,
    text: str | None,
    ocr_levels: TradeLevels | None,
) -> ExternalSignalFields:
    """Build the persisted external signal fields from message text and OCR."""
    kind: ExternalAlertKind = "TRADE_SIGNAL"
    strategy: ExternalStrategyTag = "UNKNOWN"

    parse_sources: list[str] = []

    if text:
        kind, strategy = classify_captain_message(text)
        parse_sources.append("text")

    symbol: str | None = None
    timeframe: str | None = None
    direction: Literal["BUY", "SELL"] | None = None

    if text and kind == "TRADE_SIGNAL":
        parsed = parse_captain_trade_signal_from_text(text)
        if parsed:
            symbol = parsed["symbol"]
            timeframe = parsed["timeframe"]
            direction = parsed["direction"]
            strategy = parsed["strategy"]

    entry_price: str | None = None
    stop_loss: str | None = None
    take_profits: list[str] | None = None
    ocr_raw_text: str | None = None

    if ocr_levels is not None:
        parse_sources.append("image")
        entry_price = str(ocr_levels.entry)
        stop_loss = str(ocr_levels.stop_loss)
        take_profits = [str(tp) for tp in ocr_levels.take_profits]
        ocr_raw_text = ocr_levels.raw_ocr_text

    parse_confidence: float | None = None
    if kind == "TRADE_SIGNAL" and symbol and timeframe and direction:
        parse_confidence = 1.0

    return {
        "kind": kind,
        "strategy": strategy,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profits": take_profits,
        "parse_confidence": parse_confidence,
        "parse_sources": parse_sources,
        "ocr_raw_text": ocr_raw_text,
    }
