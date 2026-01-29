"""
Tests for EventBus worker monitoring: slow event warnings and metrics basic fields.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig


@pytest.mark.asyncio
async def test_worker_warns_on_slow_event(caplog: pytest.LogCaptureFixture) -> None:
    factory = EventBusFactory()

    # Minimal mocks to satisfy factory interface validation
    sub_mgr = Mock()
    sub_mgr.add_subscription = AsyncMock(return_value="sub")
    sub_mgr.remove_subscription = AsyncMock(return_value=True)
    sub_mgr.get_subscriptions_for_event = AsyncMock(return_value=[])
    sub_mgr.get_subscription_count = AsyncMock(return_value=0)
    sub_mgr.get_active_subscription_count = AsyncMock(return_value=0)
    sub_mgr.record_subscription_failure = AsyncMock()
    sub_mgr.record_subscription_success = AsyncMock()

    evt_proc = Mock()
    evt_proc.process_event = AsyncMock()
    evt_proc.get_stats = AsyncMock()
    evt_proc.reset_stats = AsyncMock()

    # Build a bus with 1 worker and a 50ms slow-event threshold
    bus = factory.create_with_dependencies(
        subscription_manager=sub_mgr,
        event_processor=evt_proc,
        config=EventBusConfig(max_queue_size=10, num_workers=1, dead_letter_queue_size=5, slow_event_warning_threshold_ms=50),
    )

    # Monkeypatch the processing method to simulate slow work
    async def slow_process(event):  # noqa: ANN001
        await asyncio.sleep(0.08)

    bus._process_event_with_subscriptions = slow_process  # type: ignore[method-assign]

    caplog.set_level(logging.WARNING)
    await bus.start(num_workers=1)

    try:
        # Publish a dummy event
        from app.engine.models import BaseEvent, EventType
        from datetime import datetime

        evt = BaseEvent(event_type=EventType.CANDLE_UPDATE, timestamp=datetime.utcnow(), symbol="BTCUSDT")
        await bus.publish(evt)

        # Allow worker to process
        await asyncio.sleep(0.2)
    finally:
        await bus.stop()

    # Assert a slow processing warning was logged
    assert any("Slow event processing" in rec.getMessage() for rec in caplog.records)
