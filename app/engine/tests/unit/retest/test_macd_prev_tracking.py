"""
Unit tests for previous-bar MACD histogram tracking in the live retest path.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engine.models import Candle, FeaturesCalculatedEvent, TechnicalIndicators, TimeFrame
from app.engine.retest import engine as retest_engine_module
from app.engine.retest.engine import RetestEngine

# Accessing engine internals is intentional in these unit tests.
# ruff: noqa: SLF001

BAR_TIME = datetime(2024, 1, 2, tzinfo=UTC)


def _features_event(
    symbol: str,
    macd_histogram: Decimal | None,
    timeframe: TimeFrame = TimeFrame.M15,
) -> FeaturesCalculatedEvent:
    return FeaturesCalculatedEvent(
        timestamp=BAR_TIME,
        symbol=symbol,
        timeframe=timeframe,
        features=TechnicalIndicators(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=BAR_TIME,
            macd_histogram=macd_histogram,
            atr_14=Decimal(100),
            rsi_14=Decimal(50),
        ),
    )


def _candle(symbol: str, timeframe: TimeFrame = TimeFrame.M15) -> Candle:
    return Candle(
        venue="SPOT",
        symbol=symbol,
        timeframe=timeframe,
        open_time=BAR_TIME,
        close_time=BAR_TIME,
        open_price=Decimal(100),
        high_price=Decimal(101),
        low_price=Decimal(99),
        close_price=Decimal("100.5"),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trades=10,
        taker_buy_base_volume=Decimal(5),
        taker_buy_quote_volume=Decimal(500),
    )


@pytest.fixture
def engine_and_capture(monkeypatch: pytest.MonkeyPatch):
    from app.engine.backtest.capture_bus import CapturingEventBus
    from app.engine.bus import get_event_bus, set_event_bus

    try:
        previous_bus = get_event_bus()
    except RuntimeError:
        previous_bus = None
    set_event_bus(CapturingEventBus())
    captured: list[dict] = []

    async def capturing_analyze_retest(**kwargs):
        captured.append(kwargs["features"])
        return None

    monkeypatch.setattr(retest_engine_module, "analyze_retest", capturing_analyze_retest)
    engine = RetestEngine(config={})
    yield engine, captured
    if previous_bus is not None:
        set_event_bus(previous_bus)


def _seed_candles(engine: RetestEngine, symbol: str) -> Candle:
    candle = _candle(symbol)
    key = f"{symbol}:{candle.timeframe.value}"
    engine._recent_candles[key] = deque([candle])
    return candle


@pytest.mark.asyncio
async def test_passes_previous_bar_macd_histogram_to_confluence(
    engine_and_capture: tuple[RetestEngine, list[dict]],
) -> None:
    engine, captured = engine_and_capture
    candle = _seed_candles(engine, "BTCUSDT")

    await engine._process_features_event(_features_event("BTCUSDT", Decimal(1)))
    await engine._process_features_event(_features_event("BTCUSDT", Decimal("2.5")))
    await engine._check_for_retests(candle)

    assert captured == [
        {
            "atr": Decimal(100),
            "macd_hist": Decimal("2.5"),
            "macd_hist_prev": Decimal(1),
            "rsi": Decimal(50),
        },
    ]


@pytest.mark.asyncio
async def test_first_features_event_skips_signal_check_like_simulator(
    engine_and_capture: tuple[RetestEngine, list[dict]],
) -> None:
    engine, captured = engine_and_capture
    candle = _seed_candles(engine, "BTCUSDT")

    await engine._process_features_event(_features_event("BTCUSDT", Decimal(1)))
    await engine._check_for_retests(candle)

    assert captured == []


@pytest.mark.asyncio
async def test_previous_histogram_tracked_per_symbol_and_timeframe(
    engine_and_capture: tuple[RetestEngine, list[dict]],
) -> None:
    engine, captured = engine_and_capture
    btc_candle = _seed_candles(engine, "BTCUSDT")
    eth_candle = _seed_candles(engine, "ETHUSDT")

    await engine._process_features_event(_features_event("BTCUSDT", Decimal(1)))
    await engine._process_features_event(_features_event("ETHUSDT", Decimal(7)))
    await engine._process_features_event(_features_event("BTCUSDT", Decimal(2)))
    await engine._process_features_event(_features_event("ETHUSDT", Decimal(8)))
    await engine._check_for_retests(btc_candle)
    await engine._check_for_retests(eth_candle)

    assert [(f["macd_hist"], f["macd_hist_prev"]) for f in captured] == [
        (Decimal(2), Decimal(1)),
        (Decimal(8), Decimal(7)),
    ]


@pytest.mark.asyncio
async def test_missing_previous_histogram_value_skips_until_available(
    engine_and_capture: tuple[RetestEngine, list[dict]],
) -> None:
    engine, captured = engine_and_capture
    candle = _seed_candles(engine, "BTCUSDT")

    await engine._process_features_event(_features_event("BTCUSDT", None))
    await engine._process_features_event(_features_event("BTCUSDT", Decimal(3)))
    await engine._check_for_retests(candle)

    assert captured == []

    await engine._process_features_event(_features_event("BTCUSDT", Decimal(4)))
    await engine._check_for_retests(candle)

    assert [(f["macd_hist"], f["macd_hist_prev"]) for f in captured] == [
        (Decimal(4), Decimal(3)),
    ]


@pytest.mark.asyncio
async def test_current_histogram_none_skips_instead_of_fabricating_zero(
    engine_and_capture: tuple[RetestEngine, list[dict]],
) -> None:
    engine, captured = engine_and_capture
    candle = _seed_candles(engine, "BTCUSDT")

    await engine._process_features_event(_features_event("BTCUSDT", Decimal(3)))
    await engine._process_features_event(_features_event("BTCUSDT", None))
    await engine._check_for_retests(candle)

    assert captured == []
