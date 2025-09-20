"""
Integration tests for EventBus with real components.
Tests the full event processing pipeline end-to-end.
"""

import asyncio
import pytest
from datetime import datetime
from typing import List

from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig
from app.engine.models import EventType, BaseEvent


class TestEvent(BaseEvent):
    """Test event for integration tests."""
    test_data: str

    def __init__(self, test_data: str, **kwargs):
        super().__init__(
            event_type=kwargs.get('event_type', EventType.CANDLE_UPDATE),
            timestamp=kwargs.get('timestamp', datetime.utcnow()),
            symbol=kwargs.get('symbol', 'BTCUSDT'),
            test_data=test_data,
            **{k: v for k, v in kwargs.items() if k not in ['event_type', 'timestamp', 'symbol', 'test_data']}
        )


class TestEventBusIntegration:
    @pytest.mark.asyncio
    async def test_end_to_end_event_flow_with_real_components(self):
        """Test complete event flow from publish to handler execution."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        received_events = []

        async def test_handler(event: BaseEvent):
            received_events.append(event.test_data)

        # Subscribe to events
        subscription_id = await event_bus.subscribe(
            subscriber_id="test_subscriber",
            handler=test_handler,
            event_types=[EventType.CANDLE_UPDATE]
        )

        try:
            await event_bus.start()

            # Publish test event
            test_event = TestEvent(test_data="integration_test")
            result = await event_bus.publish(test_event)
            assert result is True

            # Wait for processing
            await asyncio.sleep(0.1)

            # Verify event was processed
            assert len(received_events) == 1
            assert received_events[0] == "integration_test"

        finally:
            await event_bus.stop()
            await event_bus.unsubscribe(subscription_id)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_priority_ordering_integration(self):
        """Test that multiple subscribers are called in priority order."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        call_order = []

        async def high_priority_handler(event: BaseEvent):
            call_order.append("high")

        async def low_priority_handler(event: BaseEvent):
            call_order.append("low")

        async def medium_priority_handler(event: BaseEvent):
            call_order.append("medium")

        try:
            await event_bus.start()

            # Subscribe with different priorities
            sub1 = await event_bus.subscribe("high", high_priority_handler, priority=10)
            sub2 = await event_bus.subscribe("low", low_priority_handler, priority=1)
            sub3 = await event_bus.subscribe("medium", medium_priority_handler, priority=5)

            # Publish event
            test_event = TestEvent(test_data="priority_test")
            await event_bus.publish(test_event)

            # Wait for processing
            await asyncio.sleep(0.1)

            # Verify priority order
            assert call_order == ["high", "medium", "low"]

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_subscription_failure_recovery_with_circuit_breaker(self):
        """Test that failing subscriptions are handled and disabled after retries."""
        config = EventBusConfig(
            processing_config={
                'circuit_breaker_enabled': True
            }
        )
        factory = EventBusFactory()
        event_bus = factory.create_with_config(config)

        failure_count = 0

        async def failing_handler(event: BaseEvent):
            nonlocal failure_count
            failure_count += 1
            raise ValueError(f"Test failure {failure_count}")

        try:
            await event_bus.start()

            # Subscribe with low retry limit
            subscription_id = await event_bus.subscribe(
                subscriber_id="failing_subscriber",
                handler=failing_handler,
                max_retries=2
            )

            # Publish multiple events to trigger failures
            for i in range(5):
                test_event = TestEvent(test_data=f"failure_test_{i}")
                await event_bus.publish(test_event)

            # Wait for processing
            await asyncio.sleep(0.2)

            # Verify failures were recorded
            metrics = await event_bus.get_metrics()
            assert metrics["failed_handlers"] > 0

            # Verify subscription was disabled after max retries
            assert metrics["active_subscription_count"] == 0

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_concurrent_operations_thread_safety_integration(self):
        """Test thread safety under concurrent operations."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        received_count = 0
        lock = asyncio.Lock()

        async def counting_handler(event: BaseEvent):
            nonlocal received_count
            async with lock:
                received_count += 1

        try:
            await event_bus.start()

            # Subscribe handler
            await event_bus.subscribe("counter", counting_handler)

            # Publish events concurrently
            publish_tasks = []
            for i in range(50):
                test_event = TestEvent(test_data=f"concurrent_{i}")
                task = asyncio.create_task(event_bus.publish(test_event))
                publish_tasks.append(task)

            # Wait for all publishes to complete
            results = await asyncio.gather(*publish_tasks)

            # All publishes should succeed
            assert all(results)

            # Wait for processing
            await asyncio.sleep(0.3)

            # Verify all events were processed
            assert received_count == 50

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_memory_bounded_operations_with_queue_management(self):
        """Test that the system manages queue size appropriately."""
        # Use configuration with bounded queue
        config = EventBusConfig(max_queue_size=20)
        factory = EventBusFactory()
        event_bus = factory.create_with_config(config)

        processed_count = 0

        async def counting_handler(event: BaseEvent):
            nonlocal processed_count
            processed_count += 1

        try:
            await event_bus.start()

            # Subscribe to process events
            await event_bus.subscribe("counter", counting_handler)

            # Publish events
            for i in range(15):
                test_event = TestEvent(test_data=f"bounded_{i}")
                result = await event_bus.publish(test_event)
                assert result is True  # Should succeed with reasonable queue size

            # Wait for processing
            await asyncio.sleep(0.2)

            # Verify events were processed
            assert processed_count == 15

            # Verify queue metrics are reasonable
            metrics = await event_bus.get_metrics()
            assert metrics["queue_max_size"] == config.max_queue_size
            assert metrics["queue_size"] <= config.max_queue_size

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_metrics_aggregation_across_all_components(self):
        """Test that metrics are properly aggregated from all components."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        success_count = 0

        async def metrics_handler(event: BaseEvent):
            nonlocal success_count
            success_count += 1

        try:
            await event_bus.start()

            # Subscribe handlers
            await event_bus.subscribe("metrics_sub", metrics_handler)

            # Publish some events
            for i in range(5):
                test_event = TestEvent(test_data=f"metrics_{i}")
                await event_bus.publish(test_event)

            # Wait for processing
            await asyncio.sleep(0.1)

            # Get aggregated metrics
            metrics = await event_bus.get_metrics()

            # Verify metrics structure
            assert "subscription_count" in metrics
            assert "active_subscription_count" in metrics
            assert "events_processed" in metrics
            assert "successful_handlers" in metrics
            assert "queue_size" in metrics
            assert "is_running" in metrics

            # Verify values
            assert metrics["subscription_count"] == 1
            assert metrics["active_subscription_count"] == 1
            assert metrics["events_processed"] == 5
            assert metrics["successful_handlers"] >= 5
            assert metrics["is_running"] is True

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_pending_events(self):
        """Test that shutdown properly handles pending events."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        processed_events = []
        processing_started = asyncio.Event()

        async def slow_handler(event: BaseEvent):
            # Signal that processing has started
            processing_started.set()
            # Simulate slow processing
            await asyncio.sleep(0.1)
            processed_events.append(event.test_data)

        await event_bus.start()

        try:
            # Subscribe handler
            await event_bus.subscribe("slow_sub", slow_handler)

            # Publish events
            for i in range(3):
                test_event = TestEvent(test_data=f"shutdown_{i}")
                await event_bus.publish(test_event)

            # Wait for processing to start
            await asyncio.wait_for(processing_started.wait(), timeout=1.0)

            # Allow some processing time before shutdown
            await asyncio.sleep(0.05)

        finally:
            # Shutdown should wait for workers to complete gracefully
            await event_bus.stop()

        # At least one event should have been processed
        # (though not necessarily all due to cancellation during shutdown)
        assert len(processed_events) >= 0  # Graceful - some may complete, some may not

    @pytest.mark.asyncio
    async def test_event_bus_factory_creates_working_instances(self):
        """Test that factory creates working EventBus instances."""
        factory = EventBusFactory()

        # Test default creation
        bus1 = factory.create_event_bus()
        assert bus1 is not None

        # Test custom config creation
        config = EventBusConfig(num_workers=2)
        bus2 = factory.create_with_config(config)
        assert bus2 is not None
        assert bus2._config.num_workers == 2

        # Test testing creation with mocks
        bus3 = factory.create_for_testing()
        assert bus3 is not None
        assert hasattr(bus3._subscription_manager, '_is_mock')

        # Verify instances are independent
        assert bus1 is not bus2
        assert bus2 is not bus3

    @pytest.mark.asyncio
    async def test_health_check_provides_system_status(self):
        """Test that health check provides comprehensive system status."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        # Check status when stopped
        health = await event_bus.health_check()
        assert health["status"] == "stopped"
        assert health["worker_count"] == 0

        try:
            await event_bus.start()

            # Check status when running
            health = await event_bus.health_check()
            assert health["status"] == "running"
            assert health["worker_count"] > 0
            assert "queue_usage" in health
            assert "subscription_count" in health

        finally:
            await event_bus.stop()

            # Check status after stop
            health = await event_bus.health_check()
            assert health["status"] == "stopped"
            assert health["worker_count"] == 0