"""
Unit tests for the DI EventBus (priority, DLQ, CB, metrics).
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime

from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
from app.engine.resilience.thread_safe_circuit_breaker import CircuitBreakerState
from app.engine.models import BaseEvent, EventType


class TestEventBusFactory:
    def test_create_event_bus_returns_configured_instance(self) -> None:
        config = EventBusConfig(max_queue_size=100, num_workers=1)
        bus = EventBusFactory().create_with_config(config)
        assert bus is not None


@pytest.mark.asyncio
class TestEventBus:
    @pytest_asyncio.fixture
    async def event_bus(self) -> None:  # type: ignore[misc]
        config = EventBusConfig(max_queue_size=100, num_workers=1)
        bus = EventBusFactory().create_with_config(config)
        await bus.start()
        yield bus
        await bus.stop()

    async def test_publish_event_success(self, event_bus) -> None:
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
        )

        ok = await event_bus.publish(event)
        assert ok is True

    async def test_multiple_subscribers_receive_event(self, event_bus) -> None:
        received_events = []

        async def handler1(event) -> None:
            received_events.append(("handler1", event))

        async def handler2(event) -> None:
            received_events.append(("handler2", event))

        await event_bus.subscribe("sub1", handler1, [EventType.CANDLE_UPDATE])
        await event_bus.subscribe("sub2", handler2, [EventType.CANDLE_UPDATE])

        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
        )

        await event_bus.publish(event)
        await asyncio.sleep(0.1)  # Allow processing

        assert len(received_events) == 2
        assert ("handler1", event) in received_events
        assert ("handler2", event) in received_events

    async def test_priority_ordering(self, event_bus) -> None:
        received_order = []

        async def handler(event) -> None:
            received_order.append(event.metadata.get("priority"))

        await event_bus.subscribe("sub1", handler, priority=10)

        # Publish events with different priorities
        for priority in [1, 10, 5, 3]:
            event = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
            )
            await event_bus.publish(event, priority=priority)

        await asyncio.sleep(0.2)

        # Should be processed in priority order
        assert received_order == [10, 5, 3, 1]

    async def test_dead_letter_queue_on_failure(self, event_bus) -> None:
        async def failing_handler(event) -> None:
            raise ValueError("Simulated failure")

        await event_bus.subscribe(
            "failing_sub", failing_handler, [EventType.CANDLE_UPDATE], max_retries=1
        )

        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
        )

        await event_bus.publish(event)
        await asyncio.sleep(0.5)  # Increase wait time to ensure processing

        dead_letter_events = await event_bus.get_dead_letter_events()
        assert len(dead_letter_events) == 1
        assert dead_letter_events[0].event_id == event.event_id

    async def test_circuit_breaker_opens_on_errors(self, event_bus) -> None:
        async def failing_handler(event) -> None:
            raise ValueError("Simulated error")

        # Configure failure threshold low via factory config
        # Note: for this test fixture, we will locally construct a new bus with config overrides
        await event_bus.stop()
        cfg = EventBusConfig(max_queue_size=100, num_workers=1, processing_config={"failure_threshold": 2})
        event_bus = EventBusFactory().create_with_config(cfg)
        await event_bus.start()
        subscription_id = await event_bus.subscribe("failing_sub", failing_handler, [EventType.CANDLE_UPDATE])

        # Send 2 events that will fail (circuit breaker threshold is 2)
        for i in range(2):
            event = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
            )
            await event_bus.publish(event)
            await asyncio.sleep(0.1)  # Wait between events

        await asyncio.sleep(0.1)

        # Circuit breaker should be open after 2 failures
        status = await event_bus.get_subscription_status(subscription_id)
        assert status is not None
        assert status["circuit_breaker_state"] == CircuitBreakerState.OPEN.name

    async def test_concurrent_publish_thread_safety(self, event_bus) -> None:
        received_events = set()

        async def handler(event) -> None:
            received_events.add(event.event_id)

        await event_bus.subscribe("concurrent_sub", handler)

        # Publish many events concurrently
        tasks = []
        expected_ids = set()

        for i in range(100):
            event = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol=f"SYMBOL{i}",
            )
            expected_ids.add(event.event_id)
            tasks.append(event_bus.publish(event))

        results = await asyncio.gather(*tasks)
        await asyncio.sleep(0.5)  # Allow processing

        assert all(results)
        assert received_events == expected_ids

    async def test_subscriber_invoked_multiple_events(self, event_bus) -> None:
        count = 0

        async def handler(_):  # noqa: ANN001
            nonlocal count
            count += 1

        await event_bus.subscribe("sub", handler, [EventType.CANDLE_UPDATE])

        # Publish three events; handler should be invoked three times
        for _ in range(3):
            evt = BaseEvent(event_type=EventType.CANDLE_UPDATE, timestamp=datetime.utcnow(), symbol="BTCUSDT")
            await event_bus.publish(evt)

        await asyncio.sleep(0.3)
        assert count == 3

    async def test_metrics_accuracy(self, event_bus) -> None:
        events_to_publish = 10

        async def handler(event) -> None:
            pass

        await event_bus.subscribe("metrics_sub", handler)

        for i in range(events_to_publish):
            event = BaseEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol=f"SYMBOL{i}",
            )
            await event_bus.publish(event)

        await asyncio.sleep(0.2)

        metrics = await event_bus.get_metrics()

        assert metrics["events_processed"] == events_to_publish
        assert metrics["events_failed"] == 0
        assert metrics["queue_size"] == 0  # All processed

    async def test_taskgroup_bounded_concurrency_and_exceptions(self) -> None:
        # Configure bus with max 2 concurrent handlers and DLQ on any failure
        cfg = EventBusConfig(
            max_queue_size=100,
            num_workers=1,
            processing_config={"max_concurrent_handlers": 2},
            dlq_on_any_failure=True,
        )
        bus = EventBusFactory().create_with_config(cfg)
        await bus.start()

        current = 0
        max_seen = 0
        lock = asyncio.Lock()

        async def measured_handler(_):  # noqa: ANN001
            nonlocal current, max_seen
            async with lock:
                current += 1
                max_seen = max(max_seen, current)
            await asyncio.sleep(0.05)
            async with lock:
                current -= 1

        async def failing_handler(_):  # noqa: ANN001
            await asyncio.sleep(0.02)
            raise RuntimeError("boom")

        # Subscribe multiple handlers
        for i in range(3):
            await bus.subscribe(f"m{i}", measured_handler, [EventType.CANDLE_UPDATE])
        await bus.subscribe("fail", failing_handler, [EventType.CANDLE_UPDATE])

        evt = BaseEvent(event_type=EventType.CANDLE_UPDATE, timestamp=datetime.utcnow(), symbol="BTCUSDT")
        await bus.publish(evt)

        await asyncio.sleep(0.3)

        # Concurrency should never exceed configured bound
        assert max_seen <= 2

        # With dlq_on_any_failure, event should be in DLQ
        dlq = await bus.get_dead_letter_events()
        assert any(e.event_id == evt.event_id for e in dlq)

        await bus.stop()
