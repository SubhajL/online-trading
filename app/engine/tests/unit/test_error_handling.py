"""
Unit tests for the error handling framework.
Written first following TDD principles.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.engine.core.error_handling import (
    ErrorSeverity,
    ErrorCategory,
    ErrorContext,
    EventBusError,
    SubscriptionError,
    ProcessingError,
    QueueError,
    ConfigurationError,
    TimeoutError,
    CircuitBreakerError,
    ErrorStats,
    LoggingErrorHandler,
    MetricsErrorHandler,
    RetryableErrorHandler,
    CompositeErrorHandler,
    ErrorManager,
    error_manager,
    handle_error,
    create_error_context,
    error_boundary,
)


class TestErrorContext:
    def test_error_context_defaults(self):
        context = ErrorContext()

        assert context.error_id is not None
        assert isinstance(context.timestamp, datetime)
        assert context.category == ErrorCategory.PROCESSING
        assert context.severity == ErrorSeverity.MEDIUM
        assert context.component == ""
        assert context.operation == ""
        assert context.metadata == {}
        assert context.correlation_id is None
        assert context.retry_count == 0
        assert context.max_retries == 3

    def test_error_context_custom_values(self):
        context = ErrorContext(
            category=ErrorCategory.SUBSCRIPTION,
            severity=ErrorSeverity.HIGH,
            component="test_component",
            operation="test_operation",
            metadata={"key": "value"},
            correlation_id="test-correlation",
            retry_count=2,
            max_retries=5,
        )

        assert context.category == ErrorCategory.SUBSCRIPTION
        assert context.severity == ErrorSeverity.HIGH
        assert context.component == "test_component"
        assert context.operation == "test_operation"
        assert context.metadata == {"key": "value"}
        assert context.correlation_id == "test-correlation"
        assert context.retry_count == 2
        assert context.max_retries == 5


class TestEventBusErrors:
    def test_eventbus_error_basic(self):
        error = EventBusError("Test error")

        assert error.message == "Test error"
        assert isinstance(error.context, ErrorContext)
        assert error.cause is None
        assert isinstance(error.timestamp, datetime)

    def test_eventbus_error_with_context_and_cause(self):
        context = ErrorContext(component="test")
        cause = ValueError("Original error")

        error = EventBusError("Test error", context=context, cause=cause)

        assert error.message == "Test error"
        assert error.context is context
        assert error.cause is cause

    def test_subscription_error_sets_category_and_metadata(self):
        error = SubscriptionError("Sub error", subscription_id="sub-123")

        assert error.context.category == ErrorCategory.SUBSCRIPTION
        assert error.context.metadata["subscription_id"] == "sub-123"

    def test_processing_error_sets_category_and_event_id(self):
        from uuid import uuid4

        event_id = uuid4()

        error = ProcessingError("Process error", event_id=event_id)

        assert error.context.category == ErrorCategory.PROCESSING
        assert error.context.metadata["event_id"] == str(event_id)

    def test_queue_error_sets_category_and_queue_size(self):
        error = QueueError("Queue error", queue_size=100)

        assert error.context.category == ErrorCategory.QUEUE
        assert error.context.metadata["queue_size"] == 100

    def test_configuration_error_sets_high_severity(self):
        error = ConfigurationError("Config error", config_key="test_key")

        assert error.context.category == ErrorCategory.CONFIGURATION
        assert error.context.severity == ErrorSeverity.HIGH
        assert error.context.metadata["config_key"] == "test_key"

    def test_timeout_error_sets_timeout_metadata(self):
        error = TimeoutError("Timeout error", timeout_seconds=5.0)

        assert error.context.category == ErrorCategory.TIMEOUT
        assert error.context.metadata["timeout_seconds"] == 5.0

    def test_circuit_breaker_error_sets_high_severity(self):
        error = CircuitBreakerError("Circuit breaker open")

        assert error.context.category == ErrorCategory.CIRCUIT_BREAKER
        assert error.context.severity == ErrorSeverity.HIGH


class TestLoggingErrorHandler:
    @pytest.mark.asyncio
    async def test_logging_handler_logs_error_with_structured_data(self):
        mock_logger = Mock()
        handler = LoggingErrorHandler(mock_logger)

        error = EventBusError("Test error")
        error.context.category = ErrorCategory.PROCESSING
        error.context.severity = ErrorSeverity.MEDIUM

        result = await handler.handle_error(error)

        assert result is True
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "EventBus warning" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_logging_handler_logs_critical_error(self):
        mock_logger = Mock()
        handler = LoggingErrorHandler(mock_logger)

        error = EventBusError("Critical error")
        error.context.severity = ErrorSeverity.CRITICAL

        await handler.handle_error(error)

        mock_logger.critical.assert_called_once()

    @pytest.mark.asyncio
    async def test_logging_handler_logs_error_with_cause(self):
        mock_logger = Mock()
        handler = LoggingErrorHandler(mock_logger)

        cause = ValueError("Original error")
        error = EventBusError("Test error", cause=cause)

        await handler.handle_error(error)

        # Check that cause information is logged
        call_args = mock_logger.warning.call_args
        log_data = call_args[1]["extra"]
        assert "cause" in log_data
        assert log_data["cause"] == str(cause)

    @pytest.mark.asyncio
    async def test_logging_handler_handles_logging_failure(self):
        mock_logger = Mock()
        mock_logger.warning.side_effect = Exception("Logging failed")
        handler = LoggingErrorHandler(mock_logger)

        error = EventBusError("Test error")

        result = await handler.handle_error(error)

        assert result is False
        # Should fallback to error logging
        mock_logger.error.assert_called()


class TestMetricsErrorHandler:
    @pytest.mark.asyncio
    async def test_metrics_handler_tracks_error_counts(self):
        handler = MetricsErrorHandler()

        error1 = EventBusError("Error 1")
        error1.context.category = ErrorCategory.PROCESSING
        error1.context.severity = ErrorSeverity.MEDIUM

        error2 = EventBusError("Error 2")
        error2.context.category = ErrorCategory.SUBSCRIPTION
        error2.context.severity = ErrorSeverity.HIGH

        await handler.handle_error(error1)
        await handler.handle_error(error2)

        stats = await handler.get_stats()

        assert stats.total_errors == 2
        assert stats.errors_by_category[ErrorCategory.PROCESSING] == 1
        assert stats.errors_by_category[ErrorCategory.SUBSCRIPTION] == 1
        assert stats.errors_by_severity[ErrorSeverity.MEDIUM] == 1
        assert stats.errors_by_severity[ErrorSeverity.HIGH] == 1
        assert len(stats.recent_errors) == 2

    @pytest.mark.asyncio
    async def test_metrics_handler_limits_recent_errors(self):
        handler = MetricsErrorHandler()

        # Add more than 100 errors
        for i in range(105):
            error = EventBusError(f"Error {i}")
            await handler.handle_error(error)

        stats = await handler.get_stats()

        assert stats.total_errors == 105
        assert len(stats.recent_errors) == 100  # Should be limited

    @pytest.mark.asyncio
    async def test_metrics_handler_calculates_error_rate(self):
        handler = MetricsErrorHandler()

        # Add some errors
        for i in range(5):
            error = EventBusError(f"Error {i}")
            await handler.handle_error(error)

        stats = await handler.get_stats()

        assert stats.error_rate_per_minute == 5

    @pytest.mark.asyncio
    async def test_metrics_handler_reset_stats(self):
        handler = MetricsErrorHandler()

        error = EventBusError("Test error")
        await handler.handle_error(error)

        await handler.reset_stats()
        stats = await handler.get_stats()

        assert stats.total_errors == 0
        assert len(stats.errors_by_category) == 0
        assert len(stats.recent_errors) == 0


class TestRetryableErrorHandler:
    @pytest.mark.asyncio
    async def test_retryable_handler_should_retry_processing_error(self):
        handler = RetryableErrorHandler(max_retries=3, base_delay=0.01)

        error = ProcessingError("Temporary error")
        error.context.retry_count = 1

        result = await handler.handle_error(error)

        assert result is True
        assert error.context.retry_count == 2

    @pytest.mark.asyncio
    async def test_retryable_handler_should_not_retry_config_error(self):
        handler = RetryableErrorHandler()

        error = ConfigurationError("Config error")

        result = await handler.handle_error(error)

        assert result is False

    @pytest.mark.asyncio
    async def test_retryable_handler_should_not_retry_max_retries_exceeded(self):
        handler = RetryableErrorHandler(max_retries=2)

        error = ProcessingError("Error")
        error.context.retry_count = 2  # At max retries

        result = await handler.handle_error(error)

        assert result is False

    @pytest.mark.asyncio
    async def test_retryable_handler_exponential_backoff(self):
        handler = RetryableErrorHandler(base_delay=0.01, backoff_factor=2.0)

        error = ProcessingError("Error")
        error.context.retry_count = 2

        start_time = asyncio.get_event_loop().time()
        await handler.handle_error(error)
        end_time = asyncio.get_event_loop().time()

        # Should wait base_delay * (backoff_factor ^ retry_count)
        # 0.01 * (2 ^ 2) = 0.04 seconds
        elapsed = end_time - start_time
        assert elapsed >= 0.04


class TestCompositeErrorHandler:
    @pytest.mark.asyncio
    async def test_composite_handler_calls_all_handlers(self):
        handler1 = Mock(spec=LoggingErrorHandler)
        handler1.handle_error = AsyncMock(return_value=True)

        handler2 = Mock(spec=MetricsErrorHandler)
        handler2.handle_error = AsyncMock(return_value=True)

        composite = CompositeErrorHandler([handler1, handler2])

        error = EventBusError("Test error")
        result = await composite.handle_error(error)

        assert result is True
        handler1.handle_error.assert_called_once_with(error)
        handler2.handle_error.assert_called_once_with(error)

    @pytest.mark.asyncio
    async def test_composite_handler_returns_true_if_any_succeeds(self):
        handler1 = Mock()
        handler1.handle_error = AsyncMock(return_value=False)

        handler2 = Mock()
        handler2.handle_error = AsyncMock(return_value=True)

        composite = CompositeErrorHandler([handler1, handler2])

        error = EventBusError("Test error")
        result = await composite.handle_error(error)

        assert result is True

    @pytest.mark.asyncio
    async def test_composite_handler_handles_handler_exceptions(self):
        handler1 = Mock()
        handler1.handle_error = AsyncMock(side_effect=Exception("Handler failed"))

        handler2 = Mock()
        handler2.handle_error = AsyncMock(return_value=True)

        composite = CompositeErrorHandler([handler1, handler2])

        error = EventBusError("Test error")
        result = await composite.handle_error(error)

        assert result is True  # Second handler succeeded


class TestErrorManager:
    @pytest.mark.asyncio
    async def test_error_manager_handles_eventbus_error(self):
        manager = ErrorManager()

        error = EventBusError("Test error")
        result = await manager.handle_error(error)

        assert result is True

    @pytest.mark.asyncio
    async def test_error_manager_converts_regular_exception(self):
        manager = ErrorManager()

        error = ValueError("Regular exception")
        context = ErrorContext(component="test")

        result = await manager.handle_error(error, context)

        assert result is True

    @pytest.mark.asyncio
    async def test_error_manager_add_remove_handlers(self):
        manager = ErrorManager()
        initial_count = len(manager._handlers)

        handler = Mock()
        manager.add_handler(handler)

        assert len(manager._handlers) == initial_count + 1

        manager.remove_handler(handler)

        assert len(manager._handlers) == initial_count

    @pytest.mark.asyncio
    async def test_error_manager_get_error_stats(self):
        manager = ErrorManager()

        error = EventBusError("Test error")
        await manager.handle_error(error)

        stats = await manager.get_error_stats()

        assert stats.total_errors >= 1


class TestConvenienceFunctions:
    @pytest.mark.asyncio
    async def test_handle_error_function_uses_global_manager(self):
        error = EventBusError("Test error")

        result = await handle_error(error)

        assert result is True

    def test_create_error_context_function(self):
        context = create_error_context(
            category=ErrorCategory.SUBSCRIPTION,
            severity=ErrorSeverity.HIGH,
            component="test_component",
            operation="test_operation",
            key="value",
        )

        assert context.category == ErrorCategory.SUBSCRIPTION
        assert context.severity == ErrorSeverity.HIGH
        assert context.component == "test_component"
        assert context.operation == "test_operation"
        assert context.metadata["key"] == "value"


class TestErrorBoundary:
    @pytest.mark.asyncio
    async def test_error_boundary_async_context_manager(self):
        with patch("app.engine.core.error_handling.handle_error") as mock_handle:
            mock_handle.return_value = True

            with pytest.raises(ValueError):
                async with error_boundary("test_component", "test_operation"):
                    raise ValueError("Test error")

            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_boundary_async_decorator(self):
        with patch("app.engine.core.error_handling.handle_error") as mock_handle:
            mock_handle.return_value = True

            @error_boundary("test_component", "test_operation")
            async def failing_function():
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                await failing_function()

            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_boundary_suppresses_exception_when_reraise_false(self):
        with patch("app.engine.core.error_handling.handle_error") as mock_handle:
            mock_handle.return_value = True

            async with error_boundary("test_component", reraise=False):
                raise ValueError("Test error")

            # Should not raise exception
            mock_handle.assert_called_once()

    def test_error_boundary_sync_context_manager(self):
        with patch("app.engine.core.error_handling.logger") as mock_logger:
            with pytest.raises(ValueError):
                with error_boundary("test_component", "test_operation"):
                    raise ValueError("Test error")

            # Should log the error synchronously
            mock_logger.error.assert_called()

    def test_error_boundary_sync_decorator(self):
        with patch("app.engine.core.error_handling.logger") as mock_logger:

            @error_boundary("test_component", "test_operation")
            def failing_function():
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                failing_function()

            # Should log the error synchronously
            mock_logger.error.assert_called()


class TestErrorStats:
    def test_error_stats_defaults(self):
        stats = ErrorStats()

        assert stats.total_errors == 0
        assert stats.errors_by_category == {}
        assert stats.errors_by_severity == {}
        assert stats.recent_errors == []
        assert stats.error_rate_per_minute == 0.0
        assert isinstance(stats.last_reset, datetime)
