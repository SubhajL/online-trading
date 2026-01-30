"""Signal cooldown to prevent duplicate orders on same zone.

Supports two backends:
- In-memory dict + monotonic clock (default, for tests)
- Redis SETEX (production, survives engine restarts)
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.engine.adapters.redis.redis_adapter import RedisAdapter

logger = logging.getLogger(__name__)

COOLDOWN_PREFIX = "cooldown"


class Clock(Protocol):
    """Protocol for time source (enables testing without sleep)."""

    def monotonic(self) -> float: ...


class _SystemClock:
    """Default clock using time.monotonic()."""

    def monotonic(self) -> float:
        return time.monotonic()


class SignalCooldown:
    """Cooldown cache to prevent duplicate signals on same zone.

    Key: (symbol, timeframe, zone_id, direction)

    When ``redis`` is provided, uses Redis SETEX so cooldowns survive
    engine restarts. Falls back to in-memory dict otherwise.
    """

    def __init__(
        self,
        cooldown_seconds: int = 300,
        clock: Clock | None = None,
        redis: RedisAdapter | None = None,
    ) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock if clock is not None else _SystemClock()
        self._redis = redis
        # In-memory fallback (always maintained for fast-path / when Redis unavailable)
        self._cache: dict[str, float] = {}

    def _build_key(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
        venue: str = "",
    ) -> str:
        if venue:
            return f"{venue}:{symbol}:{timeframe}:{zone_id}:{direction}"
        return f"{symbol}:{timeframe}:{zone_id}:{direction}"

    def _purge_expired(self) -> None:
        now = self._clock.monotonic()
        expired = [k for k, expiry in self._cache.items() if expiry <= now]
        for k in expired:
            del self._cache[k]

    async def should_allow_async(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> bool:
        """Async version that checks Redis first if available."""
        key = self._build_key(symbol, timeframe, zone_id, direction)
        if self._redis is not None:
            try:
                val = await self._redis.get(key, prefix=COOLDOWN_PREFIX)
                if val is not None:
                    return False
                return True
            except Exception:
                logger.warning("Redis cooldown check failed, falling back to in-memory")
        return self.should_allow(symbol, timeframe, zone_id, direction)

    def should_allow(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> bool:
        """Check if signal is allowed (not in cooldown). Synchronous in-memory check."""
        self._purge_expired()
        key = self._build_key(symbol, timeframe, zone_id, direction)
        return key not in self._cache

    async def record_signal_async(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> None:
        """Record signal with Redis persistence if available."""
        key = self._build_key(symbol, timeframe, zone_id, direction)
        # Always update in-memory cache
        expiry = self._clock.monotonic() + self._cooldown_seconds
        self._cache[key] = expiry

        if self._redis is not None:
            try:
                await self._redis.set(
                    key,
                    "1",
                    expire=self._cooldown_seconds,
                    prefix=COOLDOWN_PREFIX,
                )
            except Exception:
                logger.warning("Redis cooldown write failed, in-memory only")

    async def try_acquire_async(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
        venue: str = "",
    ) -> bool:
        """Atomically check and reserve a cooldown slot.

        Uses Redis SET NX EX when available (single atomic command).
        Falls back to in-memory check-and-set otherwise.
        Returns True if acquired (signal allowed), False if blocked.
        """
        key = self._build_key(symbol, timeframe, zone_id, direction, venue=venue)
        if self._redis is not None:
            try:
                acquired = await self._redis.set_nx(
                    key, "1", expire=self._cooldown_seconds, prefix=COOLDOWN_PREFIX,
                )
                if acquired:
                    self._cache[key] = self._clock.monotonic() + self._cooldown_seconds
                return acquired
            except Exception:
                logger.warning("Redis cooldown acquire failed, falling back to in-memory")

        self._purge_expired()
        if key in self._cache:
            return False
        self._cache[key] = self._clock.monotonic() + self._cooldown_seconds
        return True

    def record_signal(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> None:
        """Record signal (synchronous, in-memory only). For backwards compat."""
        key = self._build_key(symbol, timeframe, zone_id, direction)
        expiry = self._clock.monotonic() + self._cooldown_seconds
        self._cache[key] = expiry
