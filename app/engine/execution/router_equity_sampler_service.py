"""RouterEquitySamplerService - Periodically samples live equity via the router.

DecisionPublisher requires fresh rows in `equity_samples` to build a risk snapshot.
In non-paper mode, the router is the natural owner of live account access (keys and
Binance account calls), so the engine polls a router internal endpoint and stores
the resulting equity value in TimescaleDB.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter

logger = logging.getLogger(__name__)


class _RouterClient(Protocol):
    async def get_internal_equity(
        self, *, venue: str | None = None
    ) -> tuple[Decimal, "datetime"]: ...


@dataclass(frozen=True)
class RouterEquitySamplerConfig:
    venue: str
    poll_interval_seconds: int = 60


class RouterEquitySamplerService:
    """Background service that periodically samples live equity from the router."""

    def __init__(
        self,
        *,
        db_adapter: TimescaleDBAdapter,
        router_client: _RouterClient,
        config: RouterEquitySamplerConfig,
        now_fn: Callable[[], "datetime"] | None = None,
    ) -> None:
        from datetime import UTC, datetime

        self._db_adapter = db_adapter
        self._router_client = router_client
        self._config = config
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            logger.debug("RouterEquitySamplerService already running")
            return
        self._running = True
        await self._sample_once()
        self._task = asyncio.create_task(self._run())
        logger.info("RouterEquitySamplerService started (venue=%s)", self._config.venue)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        logger.info("RouterEquitySamplerService stopped")

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self._config.poll_interval_seconds)
            if not self._running:
                break
            await self._sample_once()

    async def _sample_once(self) -> None:
        try:
            equity, ts = await self._router_client.get_internal_equity(
                venue=self._config.venue,
            )
            sample_time = self._now_fn()
            if sample_time.tzinfo is None:
                from datetime import UTC

                sample_time = sample_time.replace(tzinfo=UTC)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=sample_time.tzinfo)

            source_timestamp = ts
            if ts > sample_time:
                logger.warning(
                    "Router equity timestamp in the future (source=%s sample=%s)",
                    ts,
                    sample_time,
                )
                source_timestamp = None

            success = await self._db_adapter.insert_equity_sample(
                equity=equity,
                timestamp=sample_time,
                source_timestamp=source_timestamp,
            )
            if not success:
                logger.warning("Failed to insert router equity sample")
        except Exception:
            logger.exception("Error during router equity sampling")
