"""Tests for thread-safe DeadLetterQueue implementation."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.engine.bus import DeadLetterQueue
from app.engine.models import BaseEvent, EventType


class TestDeadLetterQueue:
    """Tests for DeadLetterQueue class."""

    def test_dead_letter_queue_importable(self) -> None:
        """DeadLetterQueue should be importable from bus module."""
        assert DeadLetterQueue is not None

    @pytest.mark.asyncio
    async def test_dead_letter_queue_put_and_peek(self) -> None:
        """put should add event, peek should return without removing."""
        dlq = DeadLetterQueue(maxsize=100)
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
        )

        await dlq.put(event)
        assert dlq.qsize() == 1

        # Peek should return event without removing
        events = await dlq.peek(limit=10)
        assert len(events) == 1
        assert events[0].symbol == "BTCUSDT"
        assert dlq.qsize() == 1  # Still there

    @pytest.mark.asyncio
    async def test_dead_letter_queue_drain_removes_events(self) -> None:
        """drain should return and remove events."""
        dlq = DeadLetterQueue(maxsize=100)

        for i in range(5):
            event = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.now(UTC),
                symbol=f"SYMBOL{i}",
            )
            await dlq.put(event)

        assert dlq.qsize() == 5

        # Drain 3 events
        drained = await dlq.drain(limit=3)
        assert len(drained) == 3
        assert dlq.qsize() == 2

        # Drain remaining
        drained = await dlq.drain(limit=10)
        assert len(drained) == 2
        assert dlq.qsize() == 0

    @pytest.mark.asyncio
    async def test_dead_letter_queue_peek_does_not_mutate(self) -> None:
        """peek should not change queue state."""
        dlq = DeadLetterQueue(maxsize=100)

        for i in range(3):
            event = BaseEvent(
                event_type=EventType.SMC_SIGNAL,
                timestamp=datetime.now(UTC),
                symbol=f"SYM{i}",
            )
            await dlq.put(event)

        # Peek multiple times
        for _ in range(5):
            events = await dlq.peek(limit=10)
            assert len(events) == 3

        # Queue unchanged
        assert dlq.qsize() == 3

    @pytest.mark.asyncio
    async def test_dead_letter_queue_respects_maxsize(self) -> None:
        """Queue should respect maxsize, dropping oldest when full."""
        dlq = DeadLetterQueue(maxsize=3)

        # Add 5 events to queue with maxsize 3
        for i in range(5):
            event = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.now(UTC),
                symbol=f"SYM{i}",
            )
            await dlq.put(event)

        # Should only have last 3 events
        assert dlq.qsize() == 3
        events = await dlq.peek(limit=10)
        symbols = [e.symbol for e in events]
        assert symbols == ["SYM2", "SYM3", "SYM4"]

    @pytest.mark.asyncio
    async def test_dead_letter_queue_concurrent_access(self) -> None:
        """Queue should handle concurrent put/peek without corruption."""
        dlq = DeadLetterQueue(maxsize=1000)
        event_count = 100

        async def producer(start: int) -> None:
            for i in range(start, start + event_count):
                event = BaseEvent(
                    event_type=EventType.CANDLE_UPDATE,
                    timestamp=datetime.now(UTC),
                    symbol=f"SYM{i}",
                )
                await dlq.put(event)
                await asyncio.sleep(0)  # Yield to other tasks

        async def consumer() -> int:
            total = 0
            for _ in range(10):
                events = await dlq.peek(limit=50)
                total += len(events)
                await asyncio.sleep(0.001)
            return total

        # Run producers and consumers concurrently
        await asyncio.gather(
            producer(0),
            producer(100),
            consumer(),
            consumer(),
        )

        # All events should be in queue (no corruption)
        assert dlq.qsize() == 200

    @pytest.mark.asyncio
    async def test_dead_letter_queue_empty_peek(self) -> None:
        """peek on empty queue should return empty list."""
        dlq = DeadLetterQueue(maxsize=100)
        events = await dlq.peek(limit=10)
        assert events == []

    @pytest.mark.asyncio
    async def test_dead_letter_queue_empty_drain(self) -> None:
        """drain on empty queue should return empty list."""
        dlq = DeadLetterQueue(maxsize=100)
        events = await dlq.drain(limit=10)
        assert events == []
