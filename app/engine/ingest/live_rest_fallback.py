from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
from typing import Any, Protocol

from app.engine.models import Candle, CandleOrigin, CandleUpdateEvent, TimeFrame

logger = logging.getLogger(__name__)

# Mapping of timeframe suffix to seconds multiplier
_TF_SECONDS: dict[str, int] = {
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "M": 2592000,  # 30 days for monthly timeframes
}


def _timeframe_to_seconds(tf: TimeFrame) -> int:
    """Convert TimeFrame enum value (e.g. '15m', '4h', '1M') to seconds."""
    val = tf.value
    suffix = val[-1]
    num = int(val[:-1])
    if suffix not in _TF_SECONDS:
        raise ValueError(f"Unknown timeframe suffix: {suffix!r} in {val!r}")
    return num * _TF_SECONDS[suffix]


class _EventBus(Protocol):
    async def publish(self, event: Any, priority: int = 0) -> bool: ...


class _WsClient(Protocol):
    async def health_check(self) -> dict[str, object]: ...


class _RestClient(Protocol):
    async def get_klines(
        self,
        *,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]: ...


class _IngestService(Protocol):
    async def get_latest_candle(self, symbol: str, timeframe: TimeFrame) -> Candle | None: ...


class LiveRestFallbackService:
    """REST fallback for gap-filling candles when WS delivery fails.

    Triggers gap-fill based on candle staleness per (symbol, timeframe),
    NOT based on WS stale status. This handles the "tickers alive, klines dead"
    scenario where ticker traffic keeps WS "healthy" but klines are not arriving.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        bus: _EventBus,
        rest_client: _RestClient,
        ws_client: _WsClient,
        ingest_service: _IngestService,
        symbols: list[str],
        timeframes: list[TimeFrame],
        poll_interval_seconds: int = 30,
        now_fn: Callable[[], datetime] | None = None,
        candle_stale_multiplier: float = 2.0,
    ) -> None:
        self._bus = bus
        self._rest_client = rest_client
        self._ws_client = ws_client
        self._ingest_service = ingest_service
        self._symbols = symbols
        self._timeframes = timeframes
        self._poll_interval_seconds = poll_interval_seconds
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._candle_stale_multiplier = candle_stale_multiplier

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._watermarks: dict[tuple[str, TimeFrame], datetime] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("LiveRestFallbackService started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        logger.info("LiveRestFallbackService stopped")

    async def _run(self) -> None:
        while self._running:
            await self._check_once()
            await asyncio.sleep(self._poll_interval_seconds)

    def _is_candle_stale(
        self,
        latest: Candle,
        timeframe: TimeFrame,
        now: datetime,
    ) -> bool:
        """Check if candle is stale based on timeframe and multiplier."""
        close_time = latest.close_time
        if close_time.tzinfo is None:
            close_time = close_time.replace(tzinfo=UTC)

        timeframe_seconds = _timeframe_to_seconds(timeframe)
        threshold_seconds = timeframe_seconds * self._candle_stale_multiplier
        age_seconds = (now - close_time).total_seconds()

        return age_seconds > threshold_seconds

    async def _check_once(self) -> None:
        now = self._now_fn()

        # Log WS health for observability, but don't gate on it
        try:
            ws_health = await self._ws_client.health_check()
            logger.debug("WS health during fallback check: %s", ws_health)
        except Exception:
            logger.exception("WebSocket health check failed during fallback check")

        # Check each symbol/timeframe for candle staleness
        for symbol in self._symbols:
            for timeframe in self._timeframes:
                try:
                    latest = await self._ingest_service.get_latest_candle(
                        symbol, timeframe
                    )
                    if latest is None:
                        continue

                    if not self._is_candle_stale(latest, timeframe, now):
                        continue

                    logger.info(
                        "Candle stale for %s %s, triggering REST fallback",
                        symbol,
                        timeframe.value,
                    )
                    await self._poll_symbol_timeframe(
                        now=now,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                except Exception:
                    logger.exception(
                        "REST fallback poll failed for %s %s",
                        symbol,
                        timeframe.value,
                    )

    async def _poll_symbol_timeframe(
        self,
        *,
        now: datetime,
        symbol: str,
        timeframe: TimeFrame,
    ) -> None:
        key = (symbol, timeframe)
        watermark = self._watermarks.get(key)
        if watermark is None:
            latest = await self._ingest_service.get_latest_candle(symbol, timeframe)
            if latest is None:
                return
            watermark = latest.close_time
        if watermark.tzinfo is None:
            watermark = watermark.replace(tzinfo=UTC)

        start_time = watermark + timedelta(milliseconds=1)
        candles = await self._rest_client.get_klines(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=now,
        )
        if not isinstance(candles, list) or not candles:
            return

        last_published = watermark
        for candle in candles:
            close_time = getattr(candle, "close_time", None)
            if not isinstance(close_time, datetime):
                continue
            if close_time.tzinfo is None:
                close_time = close_time.replace(tzinfo=UTC)

            if close_time > now:
                continue
            if close_time <= last_published:
                continue

            event = CandleUpdateEvent(
                timestamp=now,
                symbol=symbol,
                timeframe=timeframe,
                candle=candle,
                origin=CandleOrigin.GAP_FILL,
            )
            event.metadata["gap_fill_source"] = "rest_fallback"
            await self._bus.publish(event)
            last_published = close_time

        self._watermarks[key] = last_published
