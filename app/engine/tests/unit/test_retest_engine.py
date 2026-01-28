"""Tests for RetestEngine zone metadata propagation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.models import (
    EventType,
    RetestSignalEvent,
    TimeFrame,
)
from app.engine.retest.engine import RetestEngine


@pytest.fixture
def event_bus() -> Any:
    """Create fresh event bus for each test."""
    bus = create_event_bus()
    set_event_bus(bus)
    return bus


@pytest.mark.asyncio
async def test_emit_signal_includes_zone_metadata(event_bus: Any) -> None:
    """RetestSignalEvent.metadata should contain zone info when signal_data has zone_id."""
    await event_bus.start(num_workers=1)

    try:
        engine = RetestEngine(config={"retest": {"max_wait_bars": 8}})
        await engine.start()

        # Capture emitted signals
        signals: list[RetestSignalEvent] = []
        got_signal = asyncio.Event()

        async def on_signal(event: RetestSignalEvent) -> None:
            signals.append(event)
            got_signal.set()

        await event_bus.subscribe(
            subscriber_id="test_signal_capture",
            handler=on_signal,
            event_types=[EventType.RETEST_SIGNAL],
        )

        # Directly test _emit_signal with zone_id in signal_data
        signal_data = {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "timestamp": datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            "direction": "LONG",
            "zone_id": "zone-abc-123",
            "zone_type": "DEMAND",
            "entry": Decimal("50000"),
            "stop_loss": Decimal("49500"),
            "tp1": Decimal("50750"),
            "tp2": Decimal("51000"),
            "tp3": Decimal("51500"),
        }

        await engine._emit_signal(signal_data)
        await asyncio.wait_for(got_signal.wait(), timeout=1.0)

        assert len(signals) == 1
        event = signals[0]

        # Zone metadata should be present
        assert "zone" in event.metadata
        assert event.metadata["zone"]["zone_id"] == "zone-abc-123"
        assert event.metadata["zone"]["zone_type"] == "DEMAND"

    finally:
        await engine.stop()
        await event_bus.stop()


@pytest.mark.asyncio
async def test_emit_signal_handles_missing_zone_id(event_bus: Any) -> None:
    """RetestSignalEvent.metadata should handle missing zone_id gracefully."""
    await event_bus.start(num_workers=1)

    try:
        engine = RetestEngine(config={"retest": {"max_wait_bars": 8}})
        await engine.start()

        signals: list[RetestSignalEvent] = []
        got_signal = asyncio.Event()

        async def on_signal(event: RetestSignalEvent) -> None:
            signals.append(event)
            got_signal.set()

        await event_bus.subscribe(
            subscriber_id="test_signal_capture",
            handler=on_signal,
            event_types=[EventType.RETEST_SIGNAL],
        )

        # Signal data without zone_id
        signal_data = {
            "symbol": "ETHUSDT",
            "timeframe": "1h",
            "timestamp": datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            "direction": "SHORT",
            "entry": Decimal("3000"),
            "stop_loss": Decimal("3050"),
            "tp1": Decimal("2925"),
            "tp2": Decimal("2850"),
            "tp3": Decimal("2700"),
        }

        await engine._emit_signal(signal_data)
        await asyncio.wait_for(got_signal.wait(), timeout=1.0)

        assert len(signals) == 1
        event = signals[0]

        # Zone metadata should still exist but with None values
        assert "zone" in event.metadata
        assert event.metadata["zone"]["zone_id"] is None

    finally:
        await engine.stop()
        await event_bus.stop()
