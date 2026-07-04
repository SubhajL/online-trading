"""Tests for CHOCH direction handling in analyze_retest.

The retest analyzer receives both BOS and CHOCH breaks from the SMC engine.
CHOCH types (BULLISH_CHOCH/BEARISH_CHOCH) must map to the same trade
direction and zone side as their BOS counterparts — a bullish change of
character is a long setup against demand zones, never a short.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.retest.engine import analyze_retest

VENUE = "binance_spot"
SYMBOL = "BTCUSDT"
TF = "15m"
NOW = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

LONG_FEATURES = {
    "atr": Decimal("2"),
    "macd_hist": Decimal("1"),  # improving vs prev -> LONG momentum passes
    "macd_hist_prev": Decimal("0"),
    "rsi": Decimal("50"),  # inside both LONG (40-55) and SHORT (45-60) ranges
}
SHORT_FEATURES = {
    "atr": Decimal("2"),
    "macd_hist": Decimal("-1"),  # declining vs prev -> SHORT momentum passes
    "macd_hist_prev": Decimal("0"),
    "rsi": Decimal("50"),
}

DEMAND_ZONE = {
    "zone_id": "z-demand",
    "zone_type": "OB",
    "side": "LOW",
    "top_price": Decimal("100"),
    "bottom_price": Decimal("98"),
}
SUPPLY_ZONE = {
    "zone_id": "z-supply",
    "zone_type": "OB",
    "side": "HIGH",
    "top_price": Decimal("102"),
    "bottom_price": Decimal("100"),
}


def _candle(*, open_price: str, close: str) -> dict:
    return {
        "open_time": NOW,
        "open": Decimal(open_price),
        "close": Decimal(close),
    }


def _break_event(kind: str) -> dict:
    return {
        "timestamp": NOW - timedelta(minutes=15),
        "type": kind,
        "level": Decimal("100"),
        "strength": Decimal("1"),
    }


class TestAnalyzeRetestChochDirection:
    @pytest.mark.asyncio
    async def test_bullish_choch_with_demand_zone_yields_long(self) -> None:
        signal = await analyze_retest(
            VENUE,
            SYMBOL,
            TF,
            [_candle(open_price="99", close="100.5")],  # bullish close
            [DEMAND_ZONE],
            [_break_event("BULLISH_CHOCH")],
            LONG_FEATURES,
        )

        assert signal is not None
        assert signal["direction"] == "LONG"
        assert signal["zone_id"] == "z-demand"

    @pytest.mark.asyncio
    async def test_bearish_choch_with_supply_zone_yields_short(self) -> None:
        signal = await analyze_retest(
            VENUE,
            SYMBOL,
            TF,
            [_candle(open_price="102", close="100.5")],  # bearish close
            [SUPPLY_ZONE],
            [_break_event("BEARISH_CHOCH")],
            SHORT_FEATURES,
        )

        assert signal is not None
        assert signal["direction"] == "SHORT"
        assert signal["zone_id"] == "z-supply"

    @pytest.mark.asyncio
    async def test_bullish_choch_does_not_signal_short_against_supply_zone(self) -> None:
        signal = await analyze_retest(
            VENUE,
            SYMBOL,
            TF,
            [_candle(open_price="102", close="100.5")],  # bearish close
            [SUPPLY_ZONE],
            [_break_event("BULLISH_CHOCH")],
            SHORT_FEATURES,
        )

        assert signal is None
