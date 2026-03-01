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
    async def test_seeds_when_no_latest_candle_exists(self) -> None:
        """Seeds gap-fill from REST when no baseline candle exists for symbol/timeframe."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        bus = AsyncMock()
        rest_client = AsyncMock()
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = None
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)

        seeded_close = now - timedelta(minutes=5)
        seeded = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=seeded_close - timedelta(minutes=5),
            close_time=seeded_close,
        )
        rest_client.get_klines.return_value = [seeded]

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

        rest_client.get_klines.assert_awaited_once()
        assert bus.publish.await_count == 1

    @pytest.mark.asyncio
    async def test_does_not_seed_when_backfill_incomplete(self) -> None:
        """Avoid publishing seed candles while backfill is still running."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        bus = AsyncMock()
        rest_client = AsyncMock()
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}

        ingest_service = AsyncMock()
        ingest_service.enable_backfill = True
        ingest_service.is_backfill_complete.return_value = False
        ingest_service.get_latest_candle.return_value = None

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
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

        rest_client.get_klines.assert_not_called()
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_seed_normalizes_naive_now_to_utc(self) -> None:
        """Naive now_fn timestamps are treated as UTC for REST queries."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        bus = AsyncMock()
        rest_client = AsyncMock()
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}

        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = None

        now_naive = datetime(2026, 1, 5, 12, 0)
        seeded_close = now_naive.replace(tzinfo=UTC) - timedelta(minutes=5)
        seeded = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=seeded_close - timedelta(minutes=5),
            close_time=seeded_close,
        )
        rest_client.get_klines.return_value = [seeded]

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now_naive,
        )

        await service._check_once()

        _, kwargs = rest_client.get_klines.await_args
        assert kwargs["start_time"].tzinfo is UTC
        assert kwargs["end_time"].tzinfo is UTC

    @pytest.mark.asyncio
    async def test_publishes_only_closed_candles_as_gap_fill(self) -> None:
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # Candle must be stale: 5m * 2.0 multiplier = 10m threshold
        # 15 minutes old > 10m threshold, so it's stale
        last_close = now - timedelta(minutes=15)

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
            close_time=last_close + timedelta(minutes=5),
        )
        open_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=last_close + timedelta(minutes=5),
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
        # Candle must be stale to trigger REST poll attempt
        last_close = now - timedelta(minutes=15)

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


class TestCandleLagBasedGapFilling:
    """Tests for candle-lag-based gap filling (not WS stale-based).

    The key fix: LiveRestFallbackService should trigger gap-fill based on
    candle staleness per (symbol, timeframe), NOT based on WS stale status.
    This handles the "tickers alive, klines dead" scenario.
    """

    @pytest.mark.asyncio
    async def test_triggers_gap_fill_when_candle_stale_ws_healthy(self) -> None:
        """Gap-fill triggers when candle is stale, even if WS is healthy."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # Candle is stale: 5m timeframe, last close was 15 minutes ago (3x interval)
        stale_close_time = now - timedelta(minutes=15)

        stale_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=stale_close_time - timedelta(minutes=5),
            close_time=stale_close_time,
        )

        new_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=stale_close_time,
            close_time=stale_close_time + timedelta(minutes=5),
        )

        bus = AsyncMock()
        rest_client = AsyncMock()
        rest_client.get_klines.return_value = [new_candle]
        ws_client = AsyncMock()
        # WS is healthy (NOT stale)
        ws_client.health_check.return_value = {"connected": True, "stale": False}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = stale_candle

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
            candle_stale_multiplier=2.0,
        )

        await service._check_once()

        # Should have polled REST and published the new candle
        rest_client.get_klines.assert_awaited_once()
        assert bus.publish.await_count == 1

    @pytest.mark.asyncio
    async def test_does_not_trigger_when_candle_fresh(self) -> None:
        """No gap-fill when candle is within freshness threshold."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # Candle is fresh: 5m timeframe, last close was 3 minutes ago (< 2x = 10m)
        fresh_close_time = now - timedelta(minutes=3)

        fresh_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=fresh_close_time - timedelta(minutes=5),
            close_time=fresh_close_time,
        )

        bus = AsyncMock()
        rest_client = AsyncMock()
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = fresh_candle

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
            candle_stale_multiplier=2.0,
        )

        await service._check_once()

        rest_client.get_klines.assert_not_called()
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_polls_only_stale_symbol_timeframe_pairs(self) -> None:
        """Only polls REST for stale pairs, skips fresh ones."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)

        # BTCUSDT 5m is stale (15 min old)
        btc_stale_close = now - timedelta(minutes=15)
        btc_stale = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=btc_stale_close - timedelta(minutes=5),
            close_time=btc_stale_close,
        )

        # ETHUSDT 5m is fresh (3 min old)
        eth_fresh_close = now - timedelta(minutes=3)
        eth_fresh = _make_candle(
            symbol="ETHUSDT",
            timeframe=TimeFrame.M5,
            open_time=eth_fresh_close - timedelta(minutes=5),
            close_time=eth_fresh_close,
        )

        new_btc_candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=btc_stale_close,
            close_time=btc_stale_close + timedelta(minutes=5),
        )

        bus = AsyncMock()
        rest_client = AsyncMock()
        rest_client.get_klines.return_value = [new_btc_candle]
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}

        def get_latest_candle(symbol: str, timeframe: TimeFrame) -> Candle:
            if symbol == "BTCUSDT":
                return btc_stale
            return eth_fresh

        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.side_effect = get_latest_candle

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
            candle_stale_multiplier=2.0,
        )

        await service._check_once()

        # Should only poll for BTCUSDT (stale), not ETHUSDT (fresh)
        assert rest_client.get_klines.await_count == 1
        call_kwargs = rest_client.get_klines.await_args.kwargs
        assert call_kwargs["symbol"] == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_respects_candle_stale_multiplier_config(self) -> None:
        """Custom candle_stale_multiplier changes threshold correctly."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # 5m = 300s, with multiplier=3.0, threshold = 900s = 15 min
        # Candle age = 12 min = 720s, which is < 900s (fresh with 3.0x)
        close_time = now - timedelta(minutes=12)

        candle = _make_candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=close_time - timedelta(minutes=5),
            close_time=close_time,
        )

        bus = AsyncMock()
        rest_client = AsyncMock()
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = candle

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
            candle_stale_multiplier=3.0,  # Higher multiplier = more lenient
        )

        await service._check_once()

        # With 3.0x multiplier, 12 min is NOT stale (threshold is 15 min)
        rest_client.get_klines.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_latest_candle_gracefully(self) -> None:
        """Attempts a REST seed when no baseline candle exists."""
        from app.engine.ingest.live_rest_fallback import LiveRestFallbackService

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)

        bus = AsyncMock()
        rest_client = AsyncMock()
        rest_client.get_klines.return_value = []
        ws_client = AsyncMock()
        ws_client.health_check.return_value = {"connected": True, "stale": False}
        ingest_service = AsyncMock()
        ingest_service.get_latest_candle.return_value = None  # No candle yet

        service = LiveRestFallbackService(
            bus=bus,
            rest_client=rest_client,
            ws_client=ws_client,
            ingest_service=ingest_service,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            poll_interval_seconds=1,
            now_fn=lambda: now,
            candle_stale_multiplier=2.0,
        )

        await service._check_once()

        rest_client.get_klines.assert_awaited_once()
        bus.publish.assert_not_called()
