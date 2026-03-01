"""Unit tests for SignalCooldown."""

from __future__ import annotations

import pytest

from app.engine.core.signal_cooldown import SignalCooldown


class FakeClock:
    """Fake clock for testing without sleep."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def monotonic(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


class TestSignalCooldown:
    """Tests for SignalCooldown class."""

    def test_first_signal_always_allowed(self) -> None:
        """Fresh signal should always pass cooldown check."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        result = cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        assert result is True

    def test_same_key_blocked_within_cooldown(self) -> None:
        """Same (symbol, timeframe, zone_id, direction) blocked within cooldown."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record first signal
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Advance time but still within cooldown
        clock.advance(100)

        result = cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        assert result is False

    def test_different_zone_allowed(self) -> None:
        """Different zone_id should not be blocked."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record signal for zone_123
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Check different zone
        result = cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_456",
            direction="BUY",
        )

        assert result is True

    def test_different_timeframe_allowed(self) -> None:
        """Same zone on different timeframe should not be blocked."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record signal for 15m
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Check same zone on 1h
        result = cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="1h",
            zone_id="zone_123",
            direction="BUY",
        )

        assert result is True

    def test_opposite_direction_allowed(self) -> None:
        """Same zone with opposite direction should not be blocked."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record BUY signal
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Check SELL on same zone
        result = cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="SELL",
        )

        assert result is True

    def test_different_symbol_allowed(self) -> None:
        """Different symbol should not be blocked."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record signal for BTCUSDT
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Check ETHUSDT
        result = cooldown.should_allow(
            symbol="ETHUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        assert result is True

    def test_signal_allowed_after_expiry(self) -> None:
        """Signal should be allowed after cooldown expires."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record signal
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Advance past cooldown
        clock.advance(301)

        result = cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        assert result is True

    def test_expired_entries_purged(self) -> None:
        """Expired entries should be removed to prevent memory leak."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        # Record multiple signals
        for i in range(10):
            cooldown.record_signal(
                symbol="BTCUSDT",
                timeframe="15m",
                zone_id=f"zone_{i}",
                direction="BUY",
            )

        # Verify cache has entries
        assert len(cooldown._cache) == 10

        # Advance past cooldown
        clock.advance(301)

        # Trigger purge by calling should_allow
        cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_new",
            direction="BUY",
        )

        # Expired entries should be purged
        assert len(cooldown._cache) == 0

    def test_configurable_cooldown_seconds(self) -> None:
        """Custom cooldown timeout should work correctly."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=60, clock=clock)

        # Record signal
        cooldown.record_signal(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        # Still blocked at 59 seconds
        clock.advance(59)
        assert cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        ) is False

        # Allowed at 61 seconds
        clock.advance(2)
        assert cooldown.should_allow(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        ) is True

    def test_build_key_format(self) -> None:
        """Cache key should have consistent format."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock)

        key = cooldown._build_key(
            symbol="BTCUSDT",
            timeframe="15m",
            zone_id="zone_123",
            direction="BUY",
        )

        assert key == "BTCUSDT:15m:zone_123:BUY"

    def test_default_cooldown_is_300_seconds(self) -> None:
        """Default cooldown should be 300 seconds (5 minutes)."""
        cooldown = SignalCooldown()
        assert cooldown._cooldown_seconds == 300
