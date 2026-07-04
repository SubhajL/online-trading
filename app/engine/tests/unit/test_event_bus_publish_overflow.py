"""Publish must shed load when the bounded queue is full, never block.

A blocking put on a bounded asyncio.Queue never raises QueueFull, so the
overflow branch was dead code and overload blocked the WebSocket ingest
caller indefinitely. Overflowed events are dropped to the dead-letter queue
with a reason and publish returns False.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.engine.bus import set_event_bus
from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
from app.engine.models import ErrorEvent

QUEUE_SIZE = 4
PUBLISH_TIMEOUT = 0.5


def _make_bus(*, use_priority_queue: bool, dead_letter_queue_size: int = 10):
    cfg = EventBusConfig(
        use_priority_queue=use_priority_queue,
        dlq_on_any_failure=False,
        num_workers=1,
        max_queue_size=QUEUE_SIZE,
        dead_letter_queue_size=dead_letter_queue_size,
    )
    bus = EventBusFactory().create_with_config(cfg)
    # Accept publishes without starting workers so nothing drains the queue
    # (start() treats num_workers=0 as "use config default").
    bus._running = True
    set_event_bus(bus)
    return bus


def _make_event(n: int) -> ErrorEvent:
    return ErrorEvent(
        timestamp=datetime.now(UTC),
        component="test",
        error_type=f"probe-{n}",
        error_message="probe",
        symbol="BTCUSDT",
        metadata={},
    )


@pytest.fixture(autouse=True)
def _reset_bus():
    yield
    set_event_bus(None)


class TestPublishOverflow:
    @pytest.mark.asyncio
    async def test_publish_does_not_block_when_queue_full_fifo(self) -> None:
        bus = _make_bus(use_priority_queue=False)
        for n in range(QUEUE_SIZE):
            assert await bus.publish(_make_event(n)) is True

        result = await asyncio.wait_for(
            bus.publish(_make_event(QUEUE_SIZE)),
            timeout=PUBLISH_TIMEOUT,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_does_not_block_when_queue_full_priority(self) -> None:
        bus = _make_bus(use_priority_queue=True)
        for n in range(QUEUE_SIZE):
            assert await bus.publish(_make_event(n), priority=n) is True

        result = await asyncio.wait_for(
            bus.publish(_make_event(QUEUE_SIZE), priority=9),
            timeout=PUBLISH_TIMEOUT,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_overflow_dropped_event_lands_in_dlq_with_reason(self) -> None:
        bus = _make_bus(use_priority_queue=False)
        for n in range(QUEUE_SIZE):
            await bus.publish(_make_event(n))
        dropped = _make_event(QUEUE_SIZE)

        await asyncio.wait_for(bus.publish(dropped), timeout=PUBLISH_TIMEOUT)

        dlq_events = await bus.get_dead_letter_events()
        assert [e.event_id for e in dlq_events] == [dropped.event_id]
        assert dlq_events[0].metadata["dead_letter_reason"] == "publish_queue_full"

    @pytest.mark.asyncio
    async def test_full_dlq_drops_without_blocking(self) -> None:
        bus = _make_bus(use_priority_queue=False, dead_letter_queue_size=1)
        for n in range(QUEUE_SIZE):
            await bus.publish(_make_event(n))

        first = await asyncio.wait_for(bus.publish(_make_event(100)), timeout=PUBLISH_TIMEOUT)
        second = await asyncio.wait_for(bus.publish(_make_event(101)), timeout=PUBLISH_TIMEOUT)

        assert first is False
        assert second is False
        assert len(await bus.get_dead_letter_events()) == 1
