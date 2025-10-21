"""
Priority ordering tests for DI EventBus (app.engine.bus).
"""

import asyncio
import pytest

from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig
from app.engine.models import BaseEvent, EventType
from datetime import datetime


@pytest.mark.asyncio
async def test_events_processed_in_priority_order() -> None:
    factory = EventBusFactory()
    config = EventBusConfig(
        max_queue_size=100,
        num_workers=1,
        dead_letter_queue_size=10,
        slow_event_warning_threshold_ms=100,
    )
    # We'll enable priority queue at runtime if supported by bus
    bus = factory.create_with_config(config)

    received = []

    async def handler(evt: BaseEvent) -> None:
        received.append(evt.metadata.get("priority"))

    await bus.start()
    try:
        await bus.subscribe("h", handler, [EventType.CANDLE_UPDATE], priority=0)

        # Publish with varying priorities
        for p in [1, 10, 5, 3]:
            evt = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
            )
            await bus.publish(evt, priority=p)

        await asyncio.sleep(0.3)

        # Expect highest priority first (desc)
        assert received == [10, 5, 3, 1]
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_priority_order_with_increasing_priorities() -> None:
    factory = EventBusFactory()
    config = EventBusConfig(
        max_queue_size=100,
        num_workers=1,
        dead_letter_queue_size=10,
        slow_event_warning_threshold_ms=100,
    )
    bus = factory.create_with_config(config)

    seen = []

    async def handler(evt: BaseEvent) -> None:
        seen.append(evt.metadata.get("priority"))

    await bus.start()
    try:
        await bus.subscribe("h", handler, [EventType.CANDLE_UPDATE])

    # With a priority queue, increasing published priorities should reverse in handling
        for p in [1, 2, 3, 4]:
            evt = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="ETHUSDT",
            )
            await bus.publish(evt, priority=p)

        await asyncio.sleep(0.3)

        # Priority queue processes highest priority first
        assert seen == [4, 3, 2, 1]
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_priority_toggle_fifo_order() -> None:
    factory = EventBusFactory()
    config = EventBusConfig(
        max_queue_size=100,
        num_workers=1,
        dead_letter_queue_size=10,
        slow_event_warning_threshold_ms=100,
        use_priority_queue=False,
    )
    bus = factory.create_with_config(config)

    seen = []

    async def handler(evt: BaseEvent) -> None:
        seen.append(evt.metadata.get("priority"))

    await bus.start()
    try:
        await bus.subscribe("h", handler, [EventType.CANDLE_UPDATE])

        # Publish increasing priorities; FIFO should preserve publish order
        for p in [1, 2, 3, 4]:
            evt = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="XRPUSDT",
            )
            await bus.publish(evt, priority=p)

        await asyncio.sleep(0.3)

        assert seen == [1, 2, 3, 4]
    finally:
        await bus.stop()
