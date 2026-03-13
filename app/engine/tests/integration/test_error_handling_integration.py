"""
Integration tests for error handling framework with EventBus components.
Tests error handling patterns across the full system.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.engine.core.error_handling import (
    ErrorCategory,
    ErrorSeverity,
    EventBusError,
    ProcessingError,
    QueueError,
    SubscriptionError,
    error_boundary,
    error_manager,
    handle_error,
)
from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
from app.engine.models import BaseEvent, EventType


class TestEvent(BaseEvent):
    """Test event for error handling integration tests."""

    test_data: str

    def __init__(self, test_data: str, **kwargs) -> None:
        super().__init__(  # type: ignore[call-arg]
            event_type=kwargs.get("event_type", EventType.CANDLE_UPDATE),
            timestamp=kwargs.get("timestamp", datetime.utcnow()),
            symbol=kwargs.get("symbol", "BTCUSDT"),
            test_data=test_data,
            **{
                k: v
                for k, v in kwargs.items()
                if k not in ["event_type", "timestamp", "symbol", "test_data"]
            },
        )


class TestErrorHandlingIntegration:
    @pytest.mark.asyncio
    async def test_eventbus_error_handling_components_exist(self) -> None:
        """Test that error handling components are properly integrated."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        # Test that error handling is available and working
        test_error = ProcessingError("Test error")
        result = await handle_error(test_error)
        assert result is True

        # Verify error statistics are being tracked
        stats = await error_manager.get_error_stats()
        assert stats.total_errors >= 1

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_subscription_error_handling_on_max_subscriptions(self) -> None:
        """Test subscription manager handles max subscriptions error correctly."""
        # Create EventBus with very low subscription limit
        config = EventBusConfig(subscription_config={"max_subscriptions": 2})
        factory = EventBusFactory()
        event_bus = factory.create_with_config(config)

        try:
            # Add subscriptions up to limit
            async def dummy_handler(event: BaseEvent) -> None:
                pass

            sub1 = await event_bus.subscribe("sub1", dummy_handler)
            sub2 = await event_bus.subscribe("sub2", dummy_handler)

            # Third subscription should fail with SubscriptionError
            with pytest.raises(SubscriptionError) as exc_info:
                await event_bus.subscribe("sub3", dummy_handler)

            error = exc_info.value
            assert error.context.category == ErrorCategory.RESOURCE
            assert error.context.severity == ErrorSeverity.HIGH
            assert "Maximum number of subscriptions" in error.message

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_error_boundary_integration_with_eventbus(self) -> None:
        """Test error boundary decorator works with EventBus operations."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        errors_handled = []

        async def mock_handle_error(error, context=None) -> None:
            errors_handled.append((error, context))

        @error_boundary(
            "TestComponent",
            "test_operation",
            ErrorCategory.PROCESSING,
            handler=mock_handle_error,
        )
        async def failing_operation() -> None:
            await event_bus.start()
            # Simulate an operation that fails
            raise ValueError("Simulated failure")

        with pytest.raises(ValueError):
            await failing_operation()

        # Verify error was handled
        assert len(errors_handled) == 1
        handled_error, handled_context = errors_handled[0]
        assert isinstance(handled_error, ValueError)
        assert str(handled_error) == "Simulated failure"
        assert handled_context is not None
        assert handled_context.component == "TestComponent"
        assert handled_context.operation == "test_operation"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_error_statistics_aggregation(self) -> None:
        """Test that error statistics are properly aggregated across components."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        try:
            # Generate different types of errors
            processing_error = ProcessingError("Processing failed")
            subscription_error = SubscriptionError("Subscription failed")
            queue_error = QueueError("Queue failed")

            # Handle errors
            await handle_error(processing_error)
            await handle_error(subscription_error)
            await handle_error(queue_error)

            # Get error statistics
            stats = await error_manager.get_error_stats()

            # Verify statistics
            assert stats.total_errors >= 3
            assert stats.errors_by_category[ErrorCategory.PROCESSING] >= 1
            assert stats.errors_by_category[ErrorCategory.SUBSCRIPTION] >= 1
            assert stats.errors_by_category[ErrorCategory.QUEUE] >= 1

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_subscription_failure_tracking_with_error_handling(self) -> None:
        """Test subscription failure tracking integrates with error handling."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        try:
            await event_bus.start()

            failure_count = 0

            async def failing_handler(event: BaseEvent) -> None:
                nonlocal failure_count
                failure_count += 1
                raise ValueError(f"Handler failure {failure_count}")

            # Subscribe handler with low retry limit
            subscription_id = await event_bus.subscribe(
                "failing_sub", failing_handler, max_retries=2
            )

            # Publish events that will cause handler failures
            for i in range(5):
                event = TestEvent(test_data=f"test_{i}")
                await event_bus.publish(event)

            # Wait for processing
            await asyncio.sleep(0.2)

            # Verify failures were tracked and the subscription was eventually disabled
            status = await event_bus.get_subscription_status(subscription_id)
            assert status is not None
            assert status["is_active"] is False
            assert status["retry_count"] >= 3

            # Verify subscription was disabled after max retries
            metrics = await event_bus.get_metrics()
            assert metrics["active_subscription_count"] == 0
            assert metrics["failed_handlers"] > 0
            assert metrics["events_failed"] > 0

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_error_recovery_with_retry_handler(self) -> None:
        """Test error recovery using retryable error handler."""
        from app.engine.core.error_handling import RetryableErrorHandler

        retry_handler = RetryableErrorHandler(max_retries=2, base_delay=0.01)

        # Create a processing error that should be retryable
        error = ProcessingError("Temporary processing error")

        # First retry should succeed
        result1 = await retry_handler.handle_error(error)
        assert result1 is True
        assert error.context.retry_count == 1

        # Second retry should succeed
        result2 = await retry_handler.handle_error(error)
        assert result2 is True
        assert error.context.retry_count == 2

        # Third retry should fail (max retries exceeded)
        result3 = await retry_handler.handle_error(error)
        assert result3 is False

    @pytest.mark.asyncio
    async def test_comprehensive_error_reporting_integration(self) -> None:
        """Test comprehensive error reporting across all components."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        try:
            await event_bus.start()

            # Create various error scenarios and verify they're handled

            # 1. Subscription error
            try:
                large_config = EventBusConfig(
                    subscription_config={"max_subscriptions": 1}
                )
                limited_bus = factory.create_with_config(large_config)

                async def handler(event: BaseEvent) -> None:
                    pass

                await limited_bus.subscribe("sub1", handler)
                await limited_bus.subscribe("sub2", handler)  # Should fail
            except SubscriptionError:
                pass  # Expected

            # 2. Direct error handling test
            test_errors = [
                ProcessingError("Processing failed"),
                SubscriptionError("Subscription failed"),
                QueueError("Queue failed"),
            ]

            for error in test_errors:
                result = await handle_error(error)
                assert result is True

            # Verify error statistics
            stats = await error_manager.get_error_stats()
            assert stats.total_errors >= len(test_errors)

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_error_context_propagation(self) -> None:
        """Test that error context is properly propagated through the system."""
        factory = EventBusFactory()
        config = EventBusConfig(subscription_config={"max_subscriptions": 1})
        limited_bus = factory.create_with_config(config)

        async def handler(event: BaseEvent) -> None:
            pass

        try:
            await limited_bus.subscribe("sub1", handler)

            with pytest.raises(SubscriptionError) as exc_info:
                await limited_bus.subscribe("sub2", handler)

            context = exc_info.value.context
            assert context.category == ErrorCategory.RESOURCE
            assert context.severity == ErrorSeverity.HIGH
            assert context.component == "SubscriptionManager"
            assert context.operation == "add_subscription"
            assert "max_subscriptions" in context.metadata
            assert "current_subscriptions" in context.metadata
        finally:
            await limited_bus.stop()
