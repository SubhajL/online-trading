"""
Unit tests for the refactored event bus system.
"""

import asyncio
import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from pydantic import ValidationError

from app.engine.bus_refactored import (
    EventBus,
    EventBusConfig,
    create_event_bus,
    CircuitBreakerState,
)
from app.engine.models import BaseEvent, EventType


class TestEventBusConfig:
    def test_from_env_loads_configuration(self, monkeypatch):
        monkeypatch.setenv("EVENT_BUS_MAX_QUEUE_SIZE", "5000")
        monkeypatch.setenv("EVENT_BUS_NUM_WORKERS", "2")
        monkeypatch.setenv("EVENT_BUS_ENABLE_PERSISTENCE", "false")
        monkeypatch.setenv("EVENT_BUS_DEAD_LETTER_SIZE", "500")

        config = EventBusConfig.from_env()

        assert config.max_queue_size == 5000
        assert config.num_workers == 2
        assert config.enable_persistence is False
        assert config.dead_letter_queue_size == 500

    def test_from_env_uses_defaults_when_not_set(self):
        config = EventBusConfig.from_env()

        assert config.max_queue_size == 10000
        assert config.num_workers == 4
        assert config.enable_persistence is False
        assert config.dead_letter_queue_size == 1000

    def test_validates_positive_values(self):
        with pytest.raises(ValidationError) as exc_info:
            EventBusConfig(max_queue_size=-1)
        assert "Input should be greater than 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            EventBusConfig(num_workers=0)
        assert "Input should be greater than 0" in str(exc_info.value)


class TestEventBusFactory:
    def test_create_event_bus_returns_configured_instance(self):
        config = EventBusConfig(
            max_queue_size=100, num_workers=2, enable_persistence=True
        )

        event_bus = create_event_bus(config)

        assert isinstance(event_bus, EventBus)
        assert event_bus._max_queue_size == 100
        assert event_bus._num_workers == 2
        assert event_bus._enable_persistence is True

    def test_create_event_bus_with_dependencies(self):
        config = EventBusConfig()
        persistence = MagicMock()
        metrics = MagicMock()

        event_bus = create_event_bus(
            config, persistence_backend=persistence, metrics_backend=metrics
        )

        assert event_bus._persistence_backend is persistence
        assert event_bus._metrics_backend is metrics


@pytest.mark.asyncio
class TestEventBus:
    @pytest_asyncio.fixture
    async def event_bus(self):
        config = EventBusConfig(max_queue_size=100, num_workers=1)
        bus = create_event_bus(config)
        await bus.start()
        yield bus
        await bus.stop()

    async def test_publish_event_success(self, event_bus):
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
        )

        result = await event_bus.publish(event)

        assert result.is_success is True
        assert result.event_id == event.event_id

    async def test_multiple_subscribers_receive_event(self, event_bus):
        received_events = []

        async def handler1(event):
            received_events.append(("handler1", event))

        async def handler2(event):
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

    async def test_priority_ordering(self, event_bus):
        received_order = []

        async def handler(event):
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

    async def test_dead_letter_queue_on_failure(self, event_bus):
        async def failing_handler(event):
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

    async def test_circuit_breaker_opens_on_errors(self, event_bus):
        async def failing_handler(event):
            raise ValueError("Simulated error")

        subscription_id = await event_bus.subscribe(
            "failing_sub",
            failing_handler,
            [EventType.CANDLE_UPDATE],
            circuit_breaker_threshold=2,
            max_retries=0,  # No retries to make test clearer
        )

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
        assert status.circuit_breaker_state == CircuitBreakerState.OPEN

    async def test_concurrent_publish_thread_safety(self, event_bus):
        received_events = set()

        async def handler(event):
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

        assert all(r.is_success for r in results)
        assert received_events == expected_ids

    async def test_subscriber_retry_logic(self, event_bus):
        attempt_count = 0

        async def flaky_handler(event):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Retry me")
            return "success"

        await event_bus.subscribe(
            "retry_sub",
            flaky_handler,
            [EventType.CANDLE_UPDATE],
            max_retries=3,
            retry_delay_ms=10,
        )

        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
        )

        await event_bus.publish(event)
        await asyncio.sleep(0.5)

        assert attempt_count == 3  # Initial + 2 retries

        # Event should not be in dead letter queue
        dead_letter_events = await event_bus.get_dead_letter_events()
        assert len(dead_letter_events) == 0

    async def test_metrics_accuracy(self, event_bus):
        events_to_publish = 10

        async def handler(event):
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

        assert metrics["events_published"] == events_to_publish
        assert metrics["events_processed"] == events_to_publish
        assert metrics["events_failed"] == 0
        assert metrics["queue_size"] == 0  # All processed
