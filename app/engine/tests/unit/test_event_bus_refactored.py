"""
Unit tests for refactored EventBus with dependency injection.
Written first following TDD principles.
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from app.engine.core.event_bus_factory import EventBusConfig
from app.engine.core.interfaces import (
    SubscriptionManagerInterface,
    EventProcessorInterface
)
from app.engine.core.subscription_manager import EventSubscription
from app.engine.core.event_processor import EventProcessingResult, EventProcessingStats
from app.engine.types import EventType, BaseEvent
from uuid import uuid4


class TestEvent(BaseEvent):
    """Test event for EventBus tests."""
    test_data: str

    def __init__(self, test_data: str, **kwargs):
        super().__init__(
            event_type=kwargs.get('event_type', EventType.CANDLE_UPDATE),
            timestamp=kwargs.get('timestamp', datetime.utcnow()),
            symbol=kwargs.get('symbol', 'BTCUSDT'),
            test_data=test_data,
            **{k: v for k, v in kwargs.items() if k not in ['event_type', 'timestamp', 'symbol', 'test_data']}
        )


class TestRefactoredEventBus:
    @pytest.mark.asyncio
    async def test_event_bus_initialization_with_dependencies(self):
        from app.engine.bus import EventBus

        # Create mock dependencies
        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        event_processor = Mock(spec=EventProcessorInterface)
        config = EventBusConfig()

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=config
        )

        assert event_bus._subscription_manager is subscription_manager
        assert event_bus._event_processor is event_processor
        assert event_bus._config is config
        assert not event_bus._running

    @pytest.mark.asyncio
    async def test_event_bus_publish_queues_event_successfully(self):
        from app.engine.bus import EventBus

        # Create mock dependencies
        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        event_processor = Mock(spec=EventProcessorInterface)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        event = TestEvent(test_data="test")

        # Start event bus to enable processing
        await event_bus.start()

        try:
            result = await event_bus.publish(event)

            assert result is True
            # Event should be in queue
            assert event_bus._event_queue.qsize() == 1

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_event_bus_subscribe_delegates_to_manager(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager.add_subscription = AsyncMock(return_value="test-sub-id")

        event_processor = Mock(spec=EventProcessorInterface)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        async def test_handler(event: BaseEvent):
            pass

        subscription_id = await event_bus.subscribe(
            subscriber_id="test_subscriber",
            handler=test_handler,
            event_types=[EventType.CANDLE_UPDATE],
            priority=5,
            max_retries=3
        )

        assert subscription_id == "test-sub-id"
        subscription_manager.add_subscription.assert_called_once_with(
            subscriber_id="test_subscriber",
            handler=test_handler,
            event_types=[EventType.CANDLE_UPDATE],
            priority=5,
            max_retries=3
        )

    @pytest.mark.asyncio
    async def test_event_bus_unsubscribe_delegates_to_manager(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager.remove_subscription = AsyncMock(return_value=True)

        event_processor = Mock(spec=EventProcessorInterface)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        result = await event_bus.unsubscribe("test-sub-id")

        assert result is True
        subscription_manager.remove_subscription.assert_called_once_with("test-sub-id")

    @pytest.mark.asyncio
    async def test_event_bus_metrics_aggregation_from_components(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager.get_subscription_count = AsyncMock(return_value=5)
        subscription_manager.get_active_subscription_count = AsyncMock(return_value=4)

        mock_stats = EventProcessingStats(
            events_processed=10,
            events_failed=1,
            successful_handlers=15,
            failed_handlers=2,
            total_processing_time=1.5
        )
        event_processor = Mock(spec=EventProcessorInterface)
        event_processor.get_stats = AsyncMock(return_value=mock_stats)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        metrics = await event_bus.get_metrics()

        assert metrics["subscription_count"] == 5
        assert metrics["active_subscription_count"] == 4
        assert metrics["events_processed"] == 10
        assert metrics["events_failed"] == 1
        assert metrics["successful_handlers"] == 15
        assert metrics["failed_handlers"] == 2
        assert metrics["average_processing_time"] == 0.15  # 1.5 / 10

    @pytest.mark.asyncio
    async def test_event_bus_start_stop_lifecycle_management(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        event_processor = Mock(spec=EventProcessorInterface)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig(num_workers=2)
        )

        assert not event_bus._running
        assert len(event_bus._worker_tasks) == 0

        # Start event bus
        await event_bus.start()

        assert event_bus._running
        assert len(event_bus._worker_tasks) == 2

        # Stop event bus
        await event_bus.stop()

        assert not event_bus._running
        assert len(event_bus._worker_tasks) == 0

    @pytest.mark.asyncio
    async def test_event_bus_error_propagation_from_dependencies(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager.add_subscription = AsyncMock(side_effect=ValueError("Test error"))

        event_processor = Mock(spec=EventProcessorInterface)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        async def test_handler(event: BaseEvent):
            pass

        # Error should propagate
        with pytest.raises(ValueError) as exc_info:
            await event_bus.subscribe(
                subscriber_id="test_subscriber",
                handler=test_handler
            )

        assert "Test error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_event_bus_with_mock_dependencies_isolation(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager.add_subscription = AsyncMock(return_value="mock-sub-id")
        subscription_manager.get_subscriptions_for_event = AsyncMock(return_value=[])

        mock_result = EventProcessingResult(
            event_id=uuid4(),
            successful_handlers=0,
            failed_handlers=0,
            errors=[],
            processing_time=0.0
        )
        event_processor = Mock(spec=EventProcessorInterface)
        event_processor.process_event = AsyncMock(return_value=mock_result)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        # Should work with mocks without side effects
        async def test_handler(event: BaseEvent):
            pass

        subscription_id = await event_bus.subscribe("test", test_handler)
        assert subscription_id == "mock-sub-id"

        await event_bus.start()
        try:
            result = await event_bus.publish(TestEvent(test_data="test"))
            assert result is True
        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_event_bus_health_check_aggregates_status(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager.get_subscription_count = AsyncMock(return_value=3)
        subscription_manager.get_active_subscription_count = AsyncMock(return_value=2)

        mock_stats = EventProcessingStats(events_processed=5)
        event_processor = Mock(spec=EventProcessorInterface)
        event_processor.get_stats = AsyncMock(return_value=mock_stats)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        health = await event_bus.health_check()

        assert health["status"] == "stopped"  # Not running
        assert health["subscription_count"] == 3
        assert health["active_subscription_count"] == 2
        assert health["events_processed"] == 5

    @pytest.mark.asyncio
    async def test_event_bus_reset_metrics_delegates_to_processor(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)

        event_processor = Mock(spec=EventProcessorInterface)
        event_processor.reset_stats = AsyncMock()

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        await event_bus.reset_metrics()

        event_processor.reset_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_bus_publish_many_queues_all_events(self):
        from app.engine.bus import EventBus

        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        event_processor = Mock(spec=EventProcessorInterface)

        event_bus = EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=EventBusConfig()
        )

        events = [
            TestEvent(test_data="test1"),
            TestEvent(test_data="test2"),
            TestEvent(test_data="test3")
        ]

        await event_bus.start()
        try:
            successful_count = await event_bus.publish_many(events)

            assert successful_count == 3
            # All events should be queued
            assert event_bus._event_queue.qsize() == 3

        finally:
            await event_bus.stop()