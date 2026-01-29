"""Signal cooldown to prevent duplicate orders on same zone.

Uses dict + monotonic clock (no external dependencies like cachetools).
"""

from __future__ import annotations

import time
from typing import Protocol


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
    Uses simple dict + monotonic clock, no external dependencies.
    """

    def __init__(
        self,
        cooldown_seconds: int = 300,
        clock: Clock | None = None,
    ) -> None:
        """Initialize cooldown cache.

        Args:
            cooldown_seconds: Time in seconds before same signal is allowed again.
            clock: Optional clock for testing. Defaults to system monotonic clock.
        """
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock if clock is not None else _SystemClock()
        self._cache: dict[str, float] = {}  # key -> expiry_time

    def _build_key(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> str:
        """Build cache key from signal identifiers."""
        return f"{symbol}:{timeframe}:{zone_id}:{direction}"

    def _purge_expired(self) -> None:
        """Remove expired entries to prevent memory leak."""
        now = self._clock.monotonic()
        expired = [k for k, expiry in self._cache.items() if expiry <= now]
        for k in expired:
            del self._cache[k]

    def should_allow(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> bool:
        """Check if signal is allowed (not in cooldown).

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            timeframe: Candle timeframe (e.g., 15m)
            zone_id: Zone identifier
            direction: Order direction (BUY/SELL)

        Returns:
            True if signal is allowed, False if in cooldown.
        """
        self._purge_expired()
        key = self._build_key(symbol, timeframe, zone_id, direction)
        return key not in self._cache

    def record_signal(
        self,
        symbol: str,
        timeframe: str,
        zone_id: str,
        direction: str,
    ) -> None:
        """Record signal to start cooldown period.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            timeframe: Candle timeframe (e.g., 15m)
            zone_id: Zone identifier
            direction: Order direction (BUY/SELL)
        """
        key = self._build_key(symbol, timeframe, zone_id, direction)
        expiry = self._clock.monotonic() + self._cooldown_seconds
        self._cache[key] = expiry
