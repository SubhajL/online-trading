import asyncio
from datetime import UTC, datetime

import pytest

from app.engine.core.event_processor import EventProcessor
from app.engine.core.subscription_manager import EventSubscription
from app.engine.models import BaseEvent, EventType, TimeFrame


@pytest.mark.asyncio
async def test_event_processor_serializes_keyed_handlers_across_events() -> None:
    processor = EventProcessor()

    in_handler = 0
    max_in_handler = 0
    lock = asyncio.Lock()

    async def handler(_event: BaseEvent) -> None:
        nonlocal in_handler, max_in_handler
        async with lock:
            in_handler += 1
            max_in_handler = max(max_in_handler, in_handler)
        await asyncio.sleep(0.02)
        async with lock:
            in_handler -= 1

    subscription = EventSubscription(
        subscription_id="sub-1",
        subscriber_id="stateful",
        handler=handler,
        event_types={EventType.CANDLE_UPDATE},
        priority=0,
        max_retries=0,
    )
    # New fields asserted by behavior: serialize per key
    subscription.serialize_by_key = True

    event1 = BaseEvent(
        event_type=EventType.CANDLE_UPDATE,
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
    )
    event2 = BaseEvent(
        event_type=EventType.CANDLE_UPDATE,
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
    )

    await asyncio.gather(
        processor.process_event(event1, [subscription]),
        processor.process_event(event2, [subscription]),
    )

    assert max_in_handler == 1
