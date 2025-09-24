"""Tests for retest analyzer logic."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
import asyncio

from app.engine.retest.engine import (
    analyze_retest,
    check_momentum_indicators,
    generate_entry_levels,
    has_confirmation,
    is_within_zone,
)


def test_retest_within_tolerance():
    """Verify zone entry detection with 0.25×ATR tolerance."""
    zone = {
        "top_price": Decimal("100.50"),
        "bottom_price": Decimal("99.50"),
        "zone_type": "DEMAND",
    }
    atr_value = Decimal("2.0")

    # Price exactly at zone boundary
    assert is_within_zone(Decimal("99.50"), zone, atr_value) is True

    # Price within tolerance (0.25 * 2.0 = 0.5)
    assert is_within_zone(Decimal("99.00"), zone, atr_value) is True
    assert is_within_zone(Decimal("101.00"), zone, atr_value) is True

    # Price outside tolerance
    assert is_within_zone(Decimal("98.90"), zone, atr_value) is False
    assert is_within_zone(Decimal("101.10"), zone, atr_value) is False


def test_confirmation_signals():
    """Test directional close and micro-BOS confirmation."""
    zone = {"zone_type": "DEMAND", "top_price": Decimal("100"), "bottom_price": Decimal("99")}

    # Bullish close above zone bottom for demand zone
    candle = {
        "close": Decimal("99.5"),
        "open": Decimal("98.8"),
        "low": Decimal("98.5"),
    }
    assert has_confirmation(candle, zone, None, "LONG") is True

    # Bearish close for demand zone (invalid)
    candle = {
        "close": Decimal("98.5"),
        "open": Decimal("99.2"),
        "high": Decimal("99.5"),
    }
    assert has_confirmation(candle, zone, None, "LONG") is False

    # Micro-BOS confirmation
    micro_bos = {"type": "BULLISH_BOS"}
    assert has_confirmation(None, zone, micro_bos, "LONG") is True


def test_indicator_alignment():
    """Validate MACD histogram uptick and RSI bounce conditions."""
    # Long setup: MACD uptick, RSI in bounce range
    assert check_momentum_indicators(
        macd_hist=Decimal("0.5"),
        macd_hist_prev=Decimal("0.3"),
        rsi=Decimal("45"),
        direction="LONG",
    ) is True

    # Long setup: RSI too low
    assert check_momentum_indicators(
        macd_hist=Decimal("0.5"),
        macd_hist_prev=Decimal("0.3"),
        rsi=Decimal("35"),
        direction="LONG",
    ) is False

    # Long setup: MACD not improving
    assert check_momentum_indicators(
        macd_hist=Decimal("0.3"),
        macd_hist_prev=Decimal("0.5"),
        rsi=Decimal("45"),
        direction="LONG",
    ) is False

    # Short setup: MACD downtick, RSI in resistance range
    assert check_momentum_indicators(
        macd_hist=Decimal("-0.5"),
        macd_hist_prev=Decimal("-0.3"),
        rsi=Decimal("55"),
        direction="SHORT",
    ) is True


def test_entry_level_generation():
    """Test entry, SL, and TP calculations."""
    zone = {
        "top_price": Decimal("100"),
        "bottom_price": Decimal("99"),
        "zone_type": "DEMAND",
    }
    atr = Decimal("1.0")

    levels = generate_entry_levels(zone, atr, "LONG")

    # Entry should be at zone edge
    assert levels["entry"] == Decimal("100")

    # SL should be below zone with buffer
    assert levels["stop_loss"] < Decimal("99")

    # TPs should be 1.5R, 2R, 3R
    risk = levels["entry"] - levels["stop_loss"]
    assert levels["tp1"] == levels["entry"] + (risk * Decimal("1.5"))
    assert levels["tp2"] == levels["entry"] + (risk * Decimal("2"))
    assert levels["tp3"] == levels["entry"] + (risk * Decimal("3"))


@pytest.mark.asyncio
async def test_retest_within_8_bars():
    """Ensure retests are only valid within 8 bars of BOS."""
    bos_events = [
        {
            "timestamp": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            "type": "BULLISH_BOS",
            "level": Decimal("100"),
        }
    ]

    zones = [
        {
            "zone_id": "z1",
            "top_price": Decimal("100"),
            "bottom_price": Decimal("99"),
            "zone_type": "DEMAND",
        }
    ]

    features = {
        "atr": Decimal("1.0"),
        "macd_hist": Decimal("0.5"),
        "macd_hist_prev": Decimal("0.3"),
        "rsi": Decimal("45"),
    }

    # Candles within 8 bars (assuming 5m timeframe)
    recent_candles = [
        {
            "open_time": datetime(2024, 1, 1, 10, 35, tzinfo=timezone.utc),
            "close": Decimal("99.5"),
            "open": Decimal("98.8"),
            "low": Decimal("98.5"),
        }
    ]

    result = await analyze_retest(
        symbol="BTCUSDT",
        timeframe="5m",
        candles=recent_candles,
        zones=zones,
        bos_events=bos_events,
        features=features,
    )

    # Should detect valid retest
    assert result is not None
    assert result["entry"] == Decimal("100")

    # Candles beyond 8 bars (> 40 minutes)
    old_candles = [
        {
            "open_time": datetime(2024, 1, 1, 10, 45, tzinfo=timezone.utc),
            "close": Decimal("99.5"),
            "open": Decimal("98.8"),
            "low": Decimal("98.5"),
        }
    ]

    result = await analyze_retest(
        symbol="BTCUSDT",
        timeframe="5m",
        candles=old_candles,
        zones=zones,
        bos_events=bos_events,
        features=features,
    )

    # Should not detect retest (too late)
    assert result is None