"""
Unit tests for event processor component.
Written first following TDD principles.
"""

import asyncio
import pytest
from datetime import datetime
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

from app.engine.core.event_processor import (
    EventProcessor,
    EventProcessingConfig,
    EventProcessingStats,
    EventProcessingError
)
from app.engine.core.subscription_manager import EventSubscription
from app.engine.models import EventType, BaseEvent


class TestEvent(BaseEvent):
    """Test event for processor tests."""
    test_data: str

    def __init__(self, test_data: str, **kwargs):
        super().__init__(
            event_type=kwargs.get('event_type', EventType.CANDLE_UPDATE),
            timestamp=kwargs.get('timestamp', datetime.utcnow()),
            symbol=kwargs.get('symbol', 'BTCUSDT'),
            test_data=test_data,
            **{k: v for k, v in kwargs.items() if k not in ['event_type', 'timestamp', 'symbol', 'test_data']}
        )


class TestEventProcessingConfig:
    def test_config_defaults(self):
        config = EventProcessingConfig()

        assert config.max_processing_time_seconds == 30.0
        assert config.max_concurrent_handlers == 10
        assert config.enable_metrics == True
        assert config.circuit_breaker_enabled == True

    def test_config_custom_values(self):
        config = EventProcessingConfig(
            max_processing_time_seconds=60.0,
            max_concurrent_handlers=20,
            enable_metrics=False,
            circuit_breaker_enabled=False
        )

        assert config.max_processing_time_seconds == 60.0
        assert config.max_concurrent_handlers == 20
        assert config.enable_metrics == False
        assert config.circuit_breaker_enabled == False


class TestEventProcessor:
    @pytest.mark.asyncio
    async def test_processor_initialization(self):
        config = EventProcessingConfig()
        processor = EventProcessor(config)

        stats = await processor.get_stats()
        assert stats.events_processed == 0
        assert stats.events_failed == 0
        assert stats.average_processing_time == 0.0

    @pytest.mark.asyncio
    async def test_process_event_with_single_subscription_success(self):
        processor = EventProcessor()
        event = TestEvent(test_data="test")

        # Create mock handler
        handler = AsyncMock()
        subscription = EventSubscription(
            subscription_id="test_sub",
            subscriber_id="test_subscriber",
            handler=handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        result = await processor.process_event(event, [subscription])

        assert result.successful_handlers == 1
        assert result.failed_handlers == 0
        assert len(result.errors) == 0
        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_process_event_with_multiple_subscriptions_priority_order(self):
        processor = EventProcessor()
        event = TestEvent(test_data="test")

        # Track call order
        call_order = []

        async def high_priority_handler(event: BaseEvent):
            call_order.append("high")

        async def low_priority_handler(event: BaseEvent):
            call_order.append("low")

        async def medium_priority_handler(event: BaseEvent):
            call_order.append("medium")

        subscriptions = [
            EventSubscription(
                subscription_id="low",
                subscriber_id="low_subscriber",
                handler=low_priority_handler,
                event_types={EventType.CANDLE_UPDATE},
                priority=1,
                max_retries=3
            ),
            EventSubscription(
                subscription_id="high",
                subscriber_id="high_subscriber",
                handler=high_priority_handler,
                event_types={EventType.CANDLE_UPDATE},
                priority=10,
                max_retries=3
            ),
            EventSubscription(
                subscription_id="medium",
                subscriber_id="medium_subscriber",
                handler=medium_priority_handler,
                event_types={EventType.CANDLE_UPDATE},
                priority=5,
                max_retries=3
            )
        ]

        result = await processor.process_event(event, subscriptions)

        assert result.successful_handlers == 3
        assert result.failed_handlers == 0
        # Should be called in priority order (highest first)
        assert call_order == ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_process_event_with_handler_failure(self):
        processor = EventProcessor()
        event = TestEvent(test_data="test")

        async def failing_handler(event: BaseEvent):
            raise ValueError("Test error")

        async def success_handler(event: BaseEvent):
            pass

        subscriptions = [
            EventSubscription(
                subscription_id="failing",
                subscriber_id="failing_subscriber",
                handler=failing_handler,
                event_types={EventType.CANDLE_UPDATE},
                priority=2,
                max_retries=3
            ),
            EventSubscription(
                subscription_id="success",
                subscriber_id="success_subscriber",
                handler=success_handler,
                event_types={EventType.CANDLE_UPDATE},
                priority=1,
                max_retries=3
            )
        ]

        result = await processor.process_event(event, subscriptions)

        assert result.successful_handlers == 1
        assert result.failed_handlers == 1
        assert len(result.errors) == 1
        assert "Test error" in result.errors[0].error_message
        assert result.errors[0].subscription_id == "failing"

    @pytest.mark.asyncio
    async def test_process_event_with_timeout(self):
        config = EventProcessingConfig(max_processing_time_seconds=0.1)
        processor = EventProcessor(config)
        event = TestEvent(test_data="test")

        async def slow_handler(event: BaseEvent):
            await asyncio.sleep(0.2)  # Longer than timeout

        subscription = EventSubscription(
            subscription_id="slow",
            subscriber_id="slow_subscriber",
            handler=slow_handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        result = await processor.process_event(event, [subscription])

        assert result.successful_handlers == 0
        assert result.failed_handlers == 1
        assert len(result.errors) == 1
        assert "timeout" in result.errors[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_process_event_with_sync_handler(self):
        processor = EventProcessor()
        event = TestEvent(test_data="test")

        # Non-async handler
        def sync_handler(event: BaseEvent):
            return "sync_result"

        subscription = EventSubscription(
            subscription_id="sync",
            subscriber_id="sync_subscriber",
            handler=sync_handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        result = await processor.process_event(event, [subscription])

        assert result.successful_handlers == 1
        assert result.failed_handlers == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_process_event_concurrent_processing(self):
        config = EventProcessingConfig(max_concurrent_handlers=2)
        processor = EventProcessor(config)
        event = TestEvent(test_data="test")

        # Track concurrent execution
        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def concurrent_handler(event: BaseEvent):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)

            await asyncio.sleep(0.1)  # Simulate work

            async with lock:
                concurrent_count -= 1

        subscriptions = [
            EventSubscription(
                subscription_id=f"handler_{i}",
                subscriber_id=f"subscriber_{i}",
                handler=concurrent_handler,
                event_types={EventType.CANDLE_UPDATE},
                priority=1,
                max_retries=3
            )
            for i in range(5)
        ]

        result = await processor.process_event(event, subscriptions)

        assert result.successful_handlers == 5
        assert result.failed_handlers == 0
        # Should respect concurrency limit
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_process_event_tracks_metrics(self):
        config = EventProcessingConfig(enable_metrics=True)
        processor = EventProcessor(config)
        event = TestEvent(test_data="test")

        async def handler(event: BaseEvent):
            await asyncio.sleep(0.01)  # Small delay for timing

        subscription = EventSubscription(
            subscription_id="test",
            subscriber_id="test_subscriber",
            handler=handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        await processor.process_event(event, [subscription])

        stats = await processor.get_stats()
        assert stats.events_processed == 1
        assert stats.events_failed == 0
        assert stats.average_processing_time > 0.0
        assert stats.successful_handlers == 1
        assert stats.failed_handlers == 0

    @pytest.mark.asyncio
    async def test_process_event_metrics_disabled(self):
        config = EventProcessingConfig(enable_metrics=False)
        processor = EventProcessor(config)
        event = TestEvent(test_data="test")

        async def handler(event: BaseEvent):
            pass

        subscription = EventSubscription(
            subscription_id="test",
            subscriber_id="test_subscriber",
            handler=handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        await processor.process_event(event, [subscription])

        stats = await processor.get_stats()
        # Metrics should not be tracked
        assert stats.events_processed == 0
        assert stats.average_processing_time == 0.0

    @pytest.mark.asyncio
    async def test_process_event_with_circuit_breaker(self):
        config = EventProcessingConfig(circuit_breaker_enabled=True)
        processor = EventProcessor(config)
        event = TestEvent(test_data="test")

        async def failing_handler(event: BaseEvent):
            raise Exception("Persistent failure")

        subscription = EventSubscription(
            subscription_id="failing",
            subscriber_id="failing_subscriber",
            handler=failing_handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        # Process multiple events to trigger circuit breaker
        for _ in range(10):
            await processor.process_event(event, [subscription])

        stats = await processor.get_stats()
        # Should have some circuit breaker activations
        assert stats.circuit_breaker_activations > 0

    @pytest.mark.asyncio
    async def test_reset_stats(self):
        processor = EventProcessor()
        event = TestEvent(test_data="test")

        async def handler(event: BaseEvent):
            pass

        subscription = EventSubscription(
            subscription_id="test",
            subscriber_id="test_subscriber",
            handler=handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        # Process some events
        await processor.process_event(event, [subscription])
        await processor.process_event(event, [subscription])

        # Reset stats
        await processor.reset_stats()

        stats = await processor.get_stats()
        assert stats.events_processed == 0
        assert stats.events_failed == 0
        assert stats.average_processing_time == 0.0

    @pytest.mark.asyncio
    async def test_process_event_returns_detailed_result(self):
        processor = EventProcessor()
        event = TestEvent(test_data="test")

        async def handler(event: BaseEvent):
            return "handler_result"

        subscription = EventSubscription(
            subscription_id="test",
            subscriber_id="test_subscriber",
            handler=handler,
            event_types={EventType.CANDLE_UPDATE},
            priority=1,
            max_retries=3
        )

        result = await processor.process_event(event, [subscription])

        assert hasattr(result, 'successful_handlers')
        assert hasattr(result, 'failed_handlers')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'processing_time')
        assert hasattr(result, 'event_id')
        assert result.event_id == event.event_id