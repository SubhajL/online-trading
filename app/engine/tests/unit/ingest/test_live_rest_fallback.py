from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.models import Candle, CandleOrigin, CandleUpdateEvent, TimeFrame


def _make_candle(
    *,
    symbol: str,
    timeframe: TimeFrame,
    open_time: datetime,
    close_time: datetime,
) -> Candle:
    return Candle(
        venue="spot",
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=close_time,
        open_price=Decimal(1),
        high_price=Decimal(1),
        low_price=Decimal(1),
        close_price=Decimal(1),
        volume=Decimal(1),
        quote_volume=Decimal(1),
        trades=1,
        taker_buy_base_volume=Decimal(0),
        taker_buy_quote_volume=Decimal(0),
    )


class TestLiveRestFallback:
    @pytest.mark.asyncio
    async def test_does_not_poll_rest_when_ws_not_stale(self) -> None:
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        bus = AsyncMock()
        rest_client = AsyncMock()
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = None

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
        )

        await service._check_once()

        rest_client.get_klines.assert_not_called()
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_only_closed_candles_as_gap_fill(self) -> None:
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        last_close = now - timedelta(minutes=10)

        last_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=last_close - timedelta(minutes=5),
            close_time=last_close,
        )

        closed_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=last_close,
            close_time=now - timedelta(minutes=5),
        )
        open_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=now - timedelta(minutes=5),
            close_time=now + timedelta(minutes=5),
        )

        bus = AsyncMock()
        rest_client = AsyncMock()
        rest_client.get_klines.return_value = [closed_candle, open_candle]
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": True}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = last_candle

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
        )

        await service._check_once()

        assert bus.publish.await_count == 1
        published_event = bus.publish.await_args[0][0]
        assert isinstance(published_event, CandleUpdateEvent)
        assert published_event.origin == CandleOrigin.GAP_FILL
        assert published_event.candle.close_time == closed_candle.close_time

    @pytest.mark.asyncio
    async def test_rest_failure_does_not_raise_or_publish(self) -> None:
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        last_close = now - timedelta(minutes=10)

        last_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=last_close - timedelta(minutes=5),
            close_time=last_close,
        )

        bus = AsyncMock()
        rest_client = AsyncMock()
        rest_client.get_klines.side_effect = RuntimeError("rest down")
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": True}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = last_candle

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
        )

        await service._check_once()

        bus.publish.assert_not_called()
