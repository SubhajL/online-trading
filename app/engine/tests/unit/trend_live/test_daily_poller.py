"""
Unit tests for TrendDailyCandlePoller.

The poller must only ever feed CLOSED daily candles (Binance returns the
still-open current-day kline last), must backfill gaps from its last seen
open_time, and must keep polling when persistence or one symbol's fetch fails.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.trend_live.daily_poller import (
    TrendDailyCandlePoller,
    TrendDailyPollerConfig,
    filter_closed_candles,
)
from app.engine.trend_live.decision_service import OpenSleeve

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from uuid import UUID

from uuid import uuid4

SYMBOL = "BTCUSDT"
BASE_OPEN_TIME = datetime(2026, 7, 1, tzinfo=UTC)
# Noon on 2026-07-11: day indexes 0..9 (opened 2026-07-01..10) have closed,
# day index 10 (opened 2026-07-11) is still forming.
NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _daily_candle(day_index: int, symbol: str = SYMBOL) -> Candle:
    open_time = BASE_OPEN_TIME + timedelta(days=day_index)
    close = Decimal(100 + day_index)
    return Candle(
        venue="SPOT",
        symbol=symbol,
        timeframe=TimeFrame.D1,
        open_time=open_time,
        close_time=open_time + timedelta(days=1),
        open_price=close - 1,
        high_price=close + 1,
        low_price=close - 2,
        close_price=close,
        volume=Decimal(100),
        quote_volume=Decimal(0),
        trades=1,
        taker_buy_base_volume=Decimal(0),
        taker_buy_quote_volume=Decimal(0),
    )


class FakeRestClient:
    def __init__(self, candles: list[Candle], fail: bool = False) -> None:
        self.candles = candles
        self.fail = fail
        self.calls: list[dict[str, object]] = []
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def get_klines(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        self.calls.append(
            {"symbol": symbol, "timeframe": timeframe, "start_time": start_time, "limit": limit},
        )
        if self.fail:
            raise ConnectionError("binance unreachable")
        matching = [c for c in self.candles if c.symbol == symbol]
        if start_time is not None:
            return [c for c in matching if c.open_time >= start_time]
        return matching[-limit:]


class FakeConsumer:
    def __init__(self) -> None:
        self.warmed: list[tuple[str, list[Candle]]] = []
        self.restored: list[OpenSleeve] = []
        self.fed: list[Candle] = []

    def warmup(self, symbol: str, candles: Sequence[Candle]) -> None:
        self.warmed.append((symbol, list(candles)))

    def restore_open_sleeves(self, open_sleeves: Iterable[OpenSleeve]) -> None:
        self.restored.extend(open_sleeves)

    async def on_daily_candle(self, candle: Candle) -> None:
        self.fed.append(candle)


def _make_poller(
    rest: FakeRestClient,
    consumer: FakeConsumer,
    *,
    written: list[Candle] | None = None,
    writer_raises: bool = False,
    open_sleeves: list[OpenSleeve] | None = None,
) -> TrendDailyCandlePoller:
    async def candle_writer(candle: Candle) -> bool:
        if writer_raises:
            raise RuntimeError("db down")
        if written is not None:
            written.append(candle)
        return True

    async def sleeve_loader() -> list[OpenSleeve]:
        return open_sleeves or []

    return TrendDailyCandlePoller(
        rest_client=rest,
        service=consumer,
        config=TrendDailyPollerConfig(
            symbols=(SYMBOL,),
            poll_interval_seconds=3600,
            warmup_days=90,
        ),
        candle_writer=candle_writer,
        open_sleeve_loader=sleeve_loader if open_sleeves is not None else None,
        now_fn=lambda: NOW,
    )


def test_filter_closed_candles_drops_open_current_day() -> None:
    """The still-forming current-day kline never passes the filter."""
    candles = [_daily_candle(8), _daily_candle(9), _daily_candle(10)]  # 10 closes 2026-07-12

    closed = filter_closed_candles(candles, NOW)

    assert closed == candles[:2]


@pytest.mark.asyncio
async def test_start_warms_up_recovers_and_ignores_open_candle() -> None:
    """Startup replays only closed candles and restores open sleeves."""
    history = [_daily_candle(i) for i in range(11)]  # last one is still open
    rest = FakeRestClient(history)
    consumer = FakeConsumer()
    sleeve = OpenSleeve(
        strategy_id="tsmom28",
        symbol=SYMBOL,
        bracket_id=uuid4(),
        side="LONG",
    )
    poller = _make_poller(rest, consumer, open_sleeves=[sleeve])

    await poller.start()
    await poller.stop()

    assert (consumer.warmed, consumer.restored, consumer.fed, rest.started, rest.stopped) == (
        [(SYMBOL, history[:10])],
        [sleeve],
        [],
        True,
        True,
    )


@pytest.mark.asyncio
async def test_poll_once_feeds_and_persists_only_new_closed_candles() -> None:
    """New closed candles reach the service exactly once; the open one never."""
    history = [_daily_candle(i) for i in range(9)]  # all closed
    rest = FakeRestClient(history)
    consumer = FakeConsumer()
    written: list[Candle] = []
    poller = _make_poller(rest, consumer, written=written)
    await poller.start()

    new_closed = _daily_candle(9)
    rest.candles = [*history, new_closed, _daily_candle(10)]  # day 10 still open at NOW
    await poller.poll_once()
    await poller.poll_once()
    await poller.stop()

    assert (consumer.fed, written) == ([new_closed], [new_closed])


@pytest.mark.asyncio
async def test_poll_once_backfills_from_last_seen_open_time() -> None:
    """After warmup the poller requests klines from the next unseen day."""
    history = [_daily_candle(i) for i in range(9)]
    rest = FakeRestClient(history)
    consumer = FakeConsumer()
    poller = _make_poller(rest, consumer)
    await poller.start()

    await poller.poll_once()
    await poller.stop()

    assert rest.calls[-1]["start_time"] == history[8].open_time + timedelta(days=1)


@pytest.mark.asyncio
async def test_candle_writer_failure_does_not_block_feed() -> None:
    """Persistence is best-effort: a DB error must not starve the engines."""
    history = [_daily_candle(i) for i in range(9)]
    rest = FakeRestClient(history)
    consumer = FakeConsumer()
    poller = _make_poller(rest, consumer, writer_raises=True)
    await poller.start()

    rest.candles = [*history, _daily_candle(9)]
    await poller.poll_once()
    await poller.stop()

    assert [c.open_time for c in consumer.fed] == [BASE_OPEN_TIME + timedelta(days=9)]


@pytest.mark.asyncio
async def test_service_error_retries_candle_next_cycle() -> None:
    """A feed failure neither kills the poller nor skips the candle."""
    history = [_daily_candle(i) for i in range(9)]
    rest = FakeRestClient(history)

    class FlakyConsumer(FakeConsumer):
        def __init__(self) -> None:
            super().__init__()
            self.failures_left = 1

        async def on_daily_candle(self, candle: Candle) -> None:
            if self.failures_left > 0:
                self.failures_left -= 1
                raise ConnectionError("db down")
            await super().on_daily_candle(candle)

    consumer = FlakyConsumer()
    poller = _make_poller(rest, consumer)
    await poller.start()
    rest.candles = [*history, _daily_candle(9)]

    await poller.poll_once()
    fed_after_failure = list(consumer.fed)
    await poller.poll_once()
    await poller.stop()

    assert (fed_after_failure, [c.open_time for c in consumer.fed]) == (
        [],
        [BASE_OPEN_TIME + timedelta(days=9)],
    )


@pytest.mark.asyncio
async def test_rest_error_skips_poll_cycle_without_crashing() -> None:
    """A failed fetch is retried next cycle, not fatal."""
    rest = FakeRestClient([_daily_candle(0)], fail=True)
    consumer = FakeConsumer()
    poller = _make_poller(rest, consumer)

    await poller.start()
    await poller.poll_once()
    await poller.stop()

    assert consumer.fed == []
