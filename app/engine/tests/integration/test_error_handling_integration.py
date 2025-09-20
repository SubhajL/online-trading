"""
Integration tests for error handling framework with EventBus components.
Tests error handling patterns across the full system.
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig
from app.engine.core.error_handling import (
    ErrorCategory,
    ErrorSeverity,
    EventBusError,
    SubscriptionError,
    ProcessingError,
    QueueError,
    error_manager,
    handle_error,
    error_boundary,
)
from app.engine.models import EventType, BaseEvent


class TestEvent(BaseEvent):
    """Test event for error handling integration tests."""

    test_data: str

    def __init__(self, test_data: str, **kwargs):
        super().__init__(
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
    async def test_eventbus_error_handling_components_exist(self):
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
    async def test_subscription_error_handling_on_max_subscriptions(self):
        """Test subscription manager handles max subscriptions error correctly."""
        # Create EventBus with very low subscription limit
        config = EventBusConfig(subscription_config={"max_subscriptions": 2})
        factory = EventBusFactory()
        event_bus = factory.create_with_config(config)

        try:
            # Add subscriptions up to limit
            async def dummy_handler(event: BaseEvent):
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
    async def test_error_boundary_integration_with_eventbus(self):
        """Test error boundary decorator works with EventBus operations."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        errors_handled = []

        async def mock_handle_error(error):
            errors_handled.append(error)
            return True

        # Patch the error handling to capture errors
        with patch(
            "app.engine.core.error_handling.handle_error", side_effect=mock_handle_error
        ):

            @error_boundary("TestComponent", "test_operation", ErrorCategory.PROCESSING)
            async def failing_operation():
                await event_bus.start()
                # Simulate an operation that fails
                raise ValueError("Simulated failure")

            with pytest.raises(ValueError):
                await failing_operation()

            # Verify error was handled
            assert len(errors_handled) == 1
            handled_error = errors_handled[0]
            assert isinstance(handled_error, EventBusError)
            assert handled_error.context.component == "TestComponent"
            assert handled_error.context.operation == "test_operation"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_error_statistics_aggregation(self):
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
    async def test_subscription_failure_tracking_with_error_handling(self):
        """Test subscription failure tracking integrates with error handling."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        try:
            await event_bus.start()

            failure_count = 0

            async def failing_handler(event: BaseEvent):
                nonlocal failure_count
                failure_count += 1
                raise ValueError(f"Handler failure {failure_count}")

            # Subscribe handler with low retry limit
            subscription_id = await event_bus.subscribe(
                "failing_sub", failing_handler, max_retries=2
            )

            # Publish events that will cause handler failures
            with patch(
                "app.engine.core.error_handling.handle_error"
            ) as mock_handle_error:
                for i in range(5):
                    event = TestEvent(test_data=f"test_{i}")
                    await event_bus.publish(event)

                # Wait for processing
                await asyncio.sleep(0.2)

                # Verify error handling was called for subscription failures
                assert mock_handle_error.call_count > 0

            # Verify subscription was disabled after max retries
            metrics = await event_bus.get_metrics()
            assert metrics["active_subscription_count"] == 0

        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_error_recovery_with_retry_handler(self):
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
    async def test_comprehensive_error_reporting_integration(self):
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

                async def handler(event: BaseEvent):
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
    async def test_error_context_propagation(self):
        """Test that error context is properly propagated through the system."""
        factory = EventBusFactory()
        event_bus = factory.create_event_bus()

        captured_contexts = []

        async def mock_handle_error(error):
            if hasattr(error, "context"):
                captured_contexts.append(error.context)
            return True

        with patch(
            "app.engine.core.error_handling.handle_error", side_effect=mock_handle_error
        ):
            await event_bus.start()

            try:
                # Create a subscription error scenario
                config = EventBusConfig(subscription_config={"max_subscriptions": 1})
                limited_bus = factory.create_with_config(config)

                async def handler(event: BaseEvent):
                    pass

                await limited_bus.subscribe("sub1", handler)
                await limited_bus.subscribe("sub2", handler)
            except SubscriptionError:
                pass  # Expected

            # Verify error context was captured and contains expected metadata
            assert len(captured_contexts) > 0
            context = captured_contexts[0]

            assert context.category == ErrorCategory.RESOURCE
            assert context.severity == ErrorSeverity.HIGH
            assert context.component == "SubscriptionManager"
            assert context.operation == "add_subscription"
            assert "max_subscriptions" in context.metadata
            assert "current_subscriptions" in context.metadata

            await event_bus.stop()
