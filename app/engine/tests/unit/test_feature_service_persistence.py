"""Tests for FeatureService DB persistence of indicators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.bus import set_event_bus
from app.engine.models import Candle, CandleOrigin, CandleUpdateEvent, TimeFrame


@pytest.fixture(autouse=True)
def mock_event_bus_global() -> AsyncMock:
    mock_bus = AsyncMock()
    set_event_bus(mock_bus)
    return mock_bus


def make_test_candle(*, venue: str, idx: int) -> Candle:
    base_time = datetime.now(UTC) - timedelta(hours=100)
    return Candle(
        venue=venue,
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        open_time=base_time + timedelta(minutes=idx * 15),
        close_time=base_time + timedelta(minutes=(idx + 1) * 15),
        open_price=Decimal("50000.00") + Decimal(idx),
        high_price=Decimal("50500.00") + Decimal(idx),
        low_price=Decimal("49500.00") + Decimal(idx),
        close_price=Decimal("50250.00") + Decimal(idx),
        volume=Decimal("100.5"),
        quote_volume=Decimal("5000000.00"),
        trades=1000,
        taker_buy_base_volume=Decimal("50.0"),
        taker_buy_quote_volume=Decimal("2500000.00"),
    )


def make_candle_event(candle: Candle, origin: CandleOrigin) -> CandleUpdateEvent:
    return CandleUpdateEvent(
        timestamp=datetime.now(UTC),
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        candle=candle,
        origin=origin,
    )


@pytest.mark.asyncio
async def test_realtime_event_persists_indicators_with_candle_venue(
    mock_event_bus_global: AsyncMock,
) -> None:
    from app.engine.features.feature_service import FeatureService

    venue = "binance_spot"
    db_adapter = AsyncMock()
    db_adapter.insert_technical_indicators = AsyncMock(return_value=True)

    service = FeatureService(buffer_size=300, db_adapter=db_adapter)

    # Warm-up with enough candles (EMA200 requires >= 200).
    for i in range(250):
        candle = make_test_candle(venue=venue, idx=i)
        await service._handle_candle_update(make_candle_event(candle, CandleOrigin.BACKFILL))

    db_adapter.insert_technical_indicators.reset_mock()
    mock_event_bus_global.publish.reset_mock()

    realtime_candle = make_test_candle(venue=venue, idx=251)
    await service._handle_candle_update(make_candle_event(realtime_candle, CandleOrigin.REALTIME))

    db_adapter.insert_technical_indicators.assert_called_once()
    called_venue, indicators = db_adapter.insert_technical_indicators.call_args[0]
    assert called_venue == venue
    assert indicators.symbol == "BTCUSDT"
    assert indicators.timeframe == TimeFrame.M15
