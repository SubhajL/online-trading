"""
Unit tests for bounded priority queue with TTL.
Written first following TDD principles.
"""

import asyncio
import pytest
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.engine.core.clock import FakeClock
from app.engine.core.bounded_priority_queue import (
    BoundedPriorityQueue,
    QueueItem,
    QueueStats,
    QueueFullError
)


@dataclass
class TestMessage:
    """Test message for queue."""
    id: int
    data: str


class TestBoundedPriorityQueue:
    @pytest.mark.asyncio
    async def test_old_items_expire(self):
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=start_time)
        queue = BoundedPriorityQueue(
            max_size=10,
            ttl_seconds=60,
            clock=clock
        )

        # Add items at different times
        await queue.put_with_ttl(TestMessage(1, "old"), priority=1)

        # Advance time 30 seconds
        clock.advance(seconds=30)
        await queue.put_with_ttl(TestMessage(2, "newer"), priority=2)

        # Advance time past TTL for first item (31 more seconds = 61 total)
        clock.advance(seconds=31)

        # Add a new item to trigger cleanup
        await queue.put_with_ttl(TestMessage(3, "newest"), priority=3)

        # Old item should be expired
        items = await queue.get_all_valid()
        assert len(items) == 2
        assert items[0].data.id == 3  # Highest priority
        assert items[1].data.id == 2

    @pytest.mark.asyncio
    async def test_max_size_enforced(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=3,
            ttl_seconds=300,
            clock=clock
        )

        # Fill queue
        await queue.put_with_ttl(TestMessage(1, "a"), priority=1)
        await queue.put_with_ttl(TestMessage(2, "b"), priority=2)
        await queue.put_with_ttl(TestMessage(3, "c"), priority=3)

        # Should raise when full
        with pytest.raises(QueueFullError):
            await queue.put_with_ttl(TestMessage(4, "d"), priority=4)

    @pytest.mark.asyncio
    async def test_priority_order_maintained(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=10,
            ttl_seconds=300,
            clock=clock
        )

        # Add items in random priority order
        await queue.put_with_ttl(TestMessage(1, "low"), priority=1)
        await queue.put_with_ttl(TestMessage(3, "high"), priority=10)
        await queue.put_with_ttl(TestMessage(2, "medium"), priority=5)

        # Get items - should be in priority order
        item1 = await queue.get_not_expired()
        assert item1.data.id == 3  # Highest priority

        item2 = await queue.get_not_expired()
        assert item2.data.id == 2  # Medium priority

        item3 = await queue.get_not_expired()
        assert item3.data.id == 1  # Lowest priority

    @pytest.mark.asyncio
    async def test_memory_bounded(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=100,
            ttl_seconds=10,
            clock=clock
        )

        # Add many items
        for i in range(100):
            await queue.put_with_ttl(TestMessage(i, f"msg{i}"), priority=i)

        stats = queue.get_stats()
        assert stats.current_size == 100
        assert stats.total_added == 100

        # Try to add more - should fail
        with pytest.raises(QueueFullError):
            await queue.put_with_ttl(TestMessage(101, "overflow"), priority=101)

        # Advance time to expire all old items
        clock.advance(seconds=11)

        # Trigger cleanup and add new items
        await queue.cleanup_expired()

        # Now we can add more
        for i in range(50):
            await queue.put_with_ttl(
                TestMessage(100 + i, f"new{i}"),
                priority=i
            )

        stats = queue.get_stats()
        assert stats.current_size == 50  # Only new items remain
        assert stats.expired_count == 100

    @pytest.mark.asyncio
    async def test_concurrent_put_get(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=100,
            ttl_seconds=60,
            clock=clock
        )

        received = []
        producer_done = asyncio.Event()

        async def producer(start_id: int):
            for i in range(10):
                await queue.put_with_ttl(
                    TestMessage(start_id + i, f"msg{start_id + i}"),
                    priority=start_id + i
                )
                await asyncio.sleep(0)

        async def consumer():
            # Wait for producers to finish
            await producer_done.wait()
            # Now consume all items in priority order
            for _ in range(30):
                item = await queue.get_not_expired()
                if item:
                    received.append(item.data.id)
                await asyncio.sleep(0)

        # Run producers first, then consume
        producers = [
            producer(0),
            producer(10),
            producer(20)
        ]

        # Start producers
        producer_tasks = [asyncio.create_task(p) for p in producers]

        # Start consumer
        consumer_task = asyncio.create_task(consumer())

        # Wait for producers to finish
        await asyncio.gather(*producer_tasks)
        producer_done.set()

        # Wait for consumer to finish
        await consumer_task

        # Check all received in priority order
        assert len(received) == 30
        assert received == sorted(received, reverse=True)

    @pytest.mark.asyncio
    async def test_get_not_expired_skips_expired(self):
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=start_time)
        queue = BoundedPriorityQueue(
            max_size=10,
            ttl_seconds=30,
            clock=clock
        )

        # Add items with different ages
        await queue.put_with_ttl(TestMessage(1, "old"), priority=10)
        clock.advance(seconds=20)
        await queue.put_with_ttl(TestMessage(2, "newer"), priority=5)
        clock.advance(seconds=11)  # First item now expired (31 seconds old)

        # Should skip expired and return valid
        item = await queue.get_not_expired()
        assert item.data.id == 2

        # Queue should be empty now
        item = await queue.get_not_expired()
        assert item is None

    @pytest.mark.asyncio
    async def test_custom_ttl_override(self):
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=start_time)
        queue = BoundedPriorityQueue(
            max_size=10,
            ttl_seconds=30,  # Default TTL
            clock=clock
        )

        # Add with custom TTL
        await queue.put_with_ttl(
            TestMessage(1, "short"),
            priority=1,
            custom_ttl=10
        )
        await queue.put_with_ttl(
            TestMessage(2, "long"),
            priority=2,
            custom_ttl=60
        )

        # Advance past short TTL
        clock.advance(seconds=15)

        items = await queue.get_all_valid()
        assert len(items) == 1
        assert items[0].data.id == 2  # Long TTL item survives

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=5,
            ttl_seconds=30,
            clock=clock
        )

        # Add items
        for i in range(3):
            await queue.put_with_ttl(TestMessage(i, f"msg{i}"), priority=i)

        # Get one
        await queue.get_not_expired()

        # Expire remaining items
        clock.advance(seconds=31)
        await queue.cleanup_expired()

        stats = queue.get_stats()
        assert stats.current_size == 0  # All expired
        assert stats.total_added == 3
        assert stats.total_retrieved == 1
        assert stats.expired_count == 2
        assert stats.max_size == 5

    @pytest.mark.asyncio
    async def test_wait_for_item_blocks_until_available(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=10,
            ttl_seconds=60,
            clock=clock
        )

        result = []

        async def waiter():
            item = await queue.wait_for_item(timeout=5)
            result.append(item)

        async def producer():
            await asyncio.sleep(0.01)
            await queue.put_with_ttl(TestMessage(1, "data"), priority=1)

        await asyncio.gather(waiter(), producer())

        assert len(result) == 1
        assert result[0].data.id == 1

    @pytest.mark.asyncio
    async def test_clear_removes_all_items(self):
        clock = FakeClock()
        queue = BoundedPriorityQueue(
            max_size=10,
            ttl_seconds=60,
            clock=clock
        )

        # Add items
        for i in range(5):
            await queue.put_with_ttl(TestMessage(i, f"msg{i}"), priority=i)

        # Clear
        await queue.clear()

        # Should be empty
        stats = queue.get_stats()
        assert stats.current_size == 0

        item = await queue.get_not_expired()
        assert item is None