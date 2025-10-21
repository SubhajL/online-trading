"""
Dead-letter queue tests for DI EventBus.
"""

import asyncio
import pytest
from datetime import datetime

from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig
from app.engine.models import BaseEvent, EventType


@pytest.mark.asyncio
async def test_dlq_on_all_handlers_failed() -> None:
    factory = EventBusFactory()
    config = EventBusConfig(
        max_queue_size=50,
        num_workers=1,
        dead_letter_queue_size=5,
        slow_event_warning_threshold_ms=100,
    )
    bus = factory.create_with_config(config)

    async def failing(_):  # noqa: ANN001
        raise RuntimeError("boom")

    await bus.start()
    try:
        await bus.subscribe("fail", failing, [EventType.CANDLE_UPDATE])
        evt = BaseEvent(event_type=EventType.CANDLE_UPDATE, timestamp=datetime.utcnow(), symbol="BTCUSDT")
        await bus.publish(evt)
        await asyncio.sleep(0.2)

        dlq = await bus.get_dead_letter_events()
        assert len(dlq) == 1
        assert dlq[0].event_id == evt.event_id
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_dlq_on_any_failure_when_enabled() -> None:
    factory = EventBusFactory()
    # We will toggle dlq_on_any_failure at bus-level if supported
    config = EventBusConfig(
        max_queue_size=50,
        num_workers=1,
        dead_letter_queue_size=5,
        slow_event_warning_threshold_ms=100,
        dlq_on_any_failure=True,
    )
    bus = factory.create_with_config(config)

    async def ok(_):  # noqa: ANN001
        return None

    async def failing(_):  # noqa: ANN001
        raise RuntimeError("boom")

    await bus.start()
    try:
        await bus.subscribe("ok", ok, [EventType.CANDLE_UPDATE])
        await bus.subscribe("fail", failing, [EventType.CANDLE_UPDATE])

        evt = BaseEvent(event_type=EventType.CANDLE_UPDATE, timestamp=datetime.utcnow(), symbol="ETHUSDT")
        await bus.publish(evt)
        await asyncio.sleep(0.2)

        dlq = await bus.get_dead_letter_events()
        assert len(dlq) == 1
    finally:
        await bus.stop()
