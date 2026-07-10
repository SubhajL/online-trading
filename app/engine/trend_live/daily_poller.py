"""
TrendDailyCandlePoller — REST poller feeding closed D1 candles to the trend path.

Once-a-day bars don't warrant a WS subscription: a periodic poll of the daily
klines is simpler and self-healing across restarts and gaps. Binance always
returns the still-forming current-day kline last, so only candles whose
close_time has passed are allowed through — the engines must never see an
open bar (the WS pipeline's `k.x == true` rule, expressed for REST).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Protocol

from app.engine.models import TimeFrame

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Sequence

    from app.engine.models import Candle

    from .decision_service import OpenSleeve

logger = logging.getLogger(__name__)


class KlineFetcher(Protocol):
    """The BinanceRestClient surface the poller relies on (structural)."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_klines(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]: ...


class TrendCandleConsumer(Protocol):
    """The TrendDecisionService surface the poller feeds (structural)."""

    def warmup(self, symbol: str, candles: Sequence[Candle]) -> None: ...

    def restore_open_sleeves(self, open_sleeves: Iterable[OpenSleeve]) -> None: ...

    async def on_daily_candle(self, candle: Candle) -> None: ...


@dataclass(frozen=True)
class TrendDailyPollerConfig:
    symbols: tuple[str, ...]
    poll_interval_seconds: int = 300
    warmup_days: int = 90
    fetch_limit: int = 5


def filter_closed_candles(candles: Sequence[Candle], now: datetime) -> list[Candle]:
    """Drop any kline still forming (close_time in the future)."""
    return [candle for candle in candles if candle.close_time <= now]


class TrendDailyCandlePoller:
    """Own asyncio task: warmup + recovery at start, then poll closed D1 bars."""

    def __init__(
        self,
        *,
        rest_client: KlineFetcher,
        service: TrendCandleConsumer,
        config: TrendDailyPollerConfig,
        candle_writer: Callable[[Candle], Awaitable[bool]] | None = None,
        open_sleeve_loader: Callable[[], Awaitable[list[OpenSleeve]]] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._rest_client = rest_client
        self._service = service
        self.config = config
        self._candle_writer = candle_writer
        self._open_sleeve_loader = open_sleeve_loader
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

        self._last_open_time: dict[str, datetime] = {}
        self._warmed: set[str] = set()
        self._recovered = False
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._rest_client.start()
        await self._warmup_and_recover()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "TrendDailyCandlePoller started (symbols=%s, interval=%ss)",
            ",".join(self.config.symbols),
            self.config.poll_interval_seconds,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self._rest_client.stop()
        logger.info("TrendDailyCandlePoller stopped")

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.poll_interval_seconds)
            if not self._running:
                break
            await self.poll_once()

    async def _warmup_and_recover(self) -> None:
        for symbol in self.config.symbols:
            await self._warmup_symbol(symbol)
        await self._recover_open_sleeves()

    async def _warmup_symbol(self, symbol: str) -> None:
        try:
            candles = await self._rest_client.get_klines(
                symbol,
                TimeFrame.D1,
                limit=self.config.warmup_days,
            )
        except Exception:
            logger.exception(
                "Warmup fetch failed for %s; will retry on next poll",
                symbol,
            )
            return
        closed = filter_closed_candles(candles, self._now_fn())
        self._service.warmup(symbol, closed)
        if closed:
            self._last_open_time[symbol] = closed[-1].open_time
        self._warmed.add(symbol)

    async def _recover_open_sleeves(self) -> None:
        if self._recovered or self._open_sleeve_loader is None:
            self._recovered = True
            return
        try:
            open_sleeves = await self._open_sleeve_loader()
        except Exception:
            logger.exception("Open-sleeve recovery failed; will retry on next poll")
            return
        self._service.restore_open_sleeves(open_sleeves)
        self._recovered = True

    async def poll_once(self) -> None:
        for symbol in self.config.symbols:
            if symbol not in self._warmed:
                # A cold engine must never trade; retry warmup before feeding.
                await self._warmup_symbol(symbol)
                continue
            await self._poll_symbol(symbol)
        await self._recover_open_sleeves()

    async def _poll_symbol(self, symbol: str) -> None:
        last_open_time = self._last_open_time.get(symbol)
        try:
            if last_open_time is not None:
                candles = await self._rest_client.get_klines(
                    symbol,
                    TimeFrame.D1,
                    start_time=last_open_time + timedelta(days=1),
                )
            else:
                candles = await self._rest_client.get_klines(
                    symbol,
                    TimeFrame.D1,
                    limit=self.config.fetch_limit,
                )
        except Exception:
            logger.exception("Kline poll failed for %s; retrying next cycle", symbol)
            return

        for candle in sorted(
            filter_closed_candles(candles, self._now_fn()),
            key=lambda c: c.open_time,
        ):
            if last_open_time is not None and candle.open_time <= last_open_time:
                continue
            await self._persist_candle(candle)
            try:
                await self._service.on_daily_candle(candle)
            except Exception:
                # last_open_time is not advanced, so this candle is refetched
                # and retried next cycle; one symbol's outage must not kill
                # the poll task or starve the other symbols.
                logger.exception(
                    "Trend candle feed failed for %s/%s; retrying next cycle",
                    candle.symbol,
                    candle.open_time,
                )
                return
            self._last_open_time[symbol] = candle.open_time
            last_open_time = candle.open_time

    async def _persist_candle(self, candle: Candle) -> None:
        """Best-effort audit persistence; a DB error must not starve the engines."""
        if self._candle_writer is None:
            return
        try:
            persisted = await self._candle_writer(candle)
        except Exception:
            logger.exception(
                "Failed to persist candle %s/%s",
                candle.symbol,
                candle.open_time,
            )
        else:
            if not persisted:
                logger.warning(
                    "Candle persistence returned false for %s/%s",
                    candle.symbol,
                    candle.open_time,
                )
