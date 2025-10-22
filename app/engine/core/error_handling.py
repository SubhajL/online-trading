"""
Comprehensive error handling framework for the EventBus system.

Provides structured error types, handling patterns, and recovery mechanisms
following best practices for resilient distributed systems.
"""

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from typing import Any, Callable
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for categorizing failures."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors in the EventBus system."""

    SUBSCRIPTION = "subscription"
    PROCESSING = "processing"
    QUEUE = "queue"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    VALIDATION = "validation"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class ErrorContext:
    """Rich context information for errors."""

    error_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    category: ErrorCategory = ErrorCategory.PROCESSING
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    component: str = ""
    operation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    retry_count: int = 0
    max_retries: int = 3


class EventBusError(Exception):
    """Base exception for all EventBus errors."""

    def __init__(
        self,
        message: str,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or ErrorContext()
        self.cause = cause
        self.timestamp = datetime.now(timezone.utc)


class SubscriptionError(EventBusError):
    """Error related to subscription management."""

    def __init__(
        self, message: str, subscription_id: str | None = None, **kwargs: Any
    ) -> None:
        context = kwargs.get("context", ErrorContext())
        context.category = ErrorCategory.SUBSCRIPTION
        if subscription_id:
            context.metadata["subscription_id"] = subscription_id
        super().__init__(message, context, kwargs.get("cause"))


class ProcessingError(EventBusError):
    """Error during event processing."""

    def __init__(
        self, message: str, event_id: UUID | None = None, **kwargs: Any
    ) -> None:
        context = kwargs.get("context", ErrorContext())
        context.category = ErrorCategory.PROCESSING
        if event_id:
            context.metadata["event_id"] = str(event_id)
        super().__init__(message, context, kwargs.get("cause"))


class QueueError(EventBusError):
    """Error related to queue operations."""

    def __init__(
        self, message: str, queue_size: int | None = None, **kwargs: Any
    ) -> None:
        context = kwargs.get("context", ErrorContext())
        context.category = ErrorCategory.QUEUE
        if queue_size is not None:
            context.metadata["queue_size"] = queue_size
        super().__init__(message, context, kwargs.get("cause"))


class ConfigurationError(EventBusError):
    """Error in system configuration."""

    def __init__(
        self, message: str, config_key: str | None = None, **kwargs: Any
    ) -> None:
        context = kwargs.get("context", ErrorContext())
        context.category = ErrorCategory.CONFIGURATION
        context.severity = ErrorSeverity.HIGH
        if config_key:
            context.metadata["config_key"] = config_key
        super().__init__(message, context, kwargs.get("cause"))


class TimeoutError(EventBusError):
    """Error due to operation timeout."""

    def __init__(
        self, message: str, timeout_seconds: float | None = None, **kwargs: Any
    ) -> None:
        context = kwargs.get("context", ErrorContext())
        context.category = ErrorCategory.TIMEOUT
        if timeout_seconds:
            context.metadata["timeout_seconds"] = timeout_seconds
        super().__init__(message, context, kwargs.get("cause"))


class CircuitBreakerError(EventBusError):
    """Error when circuit breaker is open."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        context = kwargs.get("context", ErrorContext())
        context.category = ErrorCategory.CIRCUIT_BREAKER
        context.severity = ErrorSeverity.HIGH
        super().__init__(message, context, kwargs.get("cause"))


@dataclass
class ErrorStats:
    """Statistics for error tracking."""

    total_errors: int = 0
    errors_by_category: dict[ErrorCategory, int] = field(default_factory=dict)
    errors_by_severity: dict[ErrorSeverity, int] = field(default_factory=dict)
    recent_errors: list[ErrorContext] = field(default_factory=list)
    error_rate_per_minute: float = 0.0
    last_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ErrorHandler(ABC):
    """Abstract base class for error handlers."""

    @abstractmethod
    async def handle_error(self, error: EventBusError) -> bool:
        """
        Handle an error.

        Args:
            error: The error to handle

        Returns:
            True if error was handled successfully
        """


class LoggingErrorHandler(ErrorHandler):
    """Error handler that logs errors with structured information."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    async def handle_error(self, error: EventBusError) -> bool:
        """Log error with structured context."""
        try:
            log_data = {
                "error_id": error.context.error_id,
                "category": error.context.category.value,
                "severity": error.context.severity.value,
                "component": error.context.component,
                "operation": error.context.operation,
                "error_message": error.message,  # Use different field name to avoid conflict
                "metadata": error.context.metadata,
                "retry_count": error.context.retry_count,
            }

            if error.cause:
                log_data["cause"] = str(error.cause)
                log_data["cause_type"] = type(error.cause).__name__

            # Log at appropriate level based on severity
            if error.context.severity == ErrorSeverity.CRITICAL:
                self._logger.critical("EventBus critical error", extra=log_data)
            elif error.context.severity == ErrorSeverity.HIGH:
                self._logger.error("EventBus error", extra=log_data)
            elif error.context.severity == ErrorSeverity.MEDIUM:
                self._logger.warning("EventBus warning", extra=log_data)
            else:
                self._logger.info("EventBus info", extra=log_data)

            return True

        except Exception as e:
            # Fallback logging if structured logging fails
            self._logger.error(f"Failed to log error {error.context.error_id}: {e}")
            self._logger.error(f"Original error: {error.message}")
            return False


class MetricsErrorHandler(ErrorHandler):
    """Error handler that tracks error metrics."""

    def __init__(self) -> None:
        self._stats = ErrorStats()
        self._lock = asyncio.Lock()

    async def handle_error(self, error: EventBusError) -> bool:
        """Track error in metrics."""
        try:
            async with self._lock:
                self._stats.total_errors += 1

                # Update category count
                category = error.context.category
                self._stats.errors_by_category[category] = (
                    self._stats.errors_by_category.get(category, 0) + 1
                )

                # Update severity count
                severity = error.context.severity
                self._stats.errors_by_severity[severity] = (
                    self._stats.errors_by_severity.get(severity, 0) + 1
                )

                # Add to recent errors (keep last 100)
                self._stats.recent_errors.append(error.context)
                if len(self._stats.recent_errors) > 100:
                    self._stats.recent_errors.pop(0)

                # Update error rate
                await self._update_error_rate()

            return True

        except Exception as e:
            logger.error(f"Failed to track error metrics: {e}")
            return False

    async def _update_error_rate(self) -> None:
        """Update error rate calculation."""
        now = datetime.now(timezone.utc)
        minute_ago = now - timedelta(minutes=1)

        recent_count = sum(
            1 for ctx in self._stats.recent_errors if ctx.timestamp >= minute_ago
        )

        self._stats.error_rate_per_minute = recent_count

    async def get_stats(self) -> ErrorStats:
        """Get current error statistics."""
        async with self._lock:
            await self._update_error_rate()
            return ErrorStats(
                total_errors=self._stats.total_errors,
                errors_by_category=self._stats.errors_by_category.copy(),
                errors_by_severity=self._stats.errors_by_severity.copy(),
                recent_errors=self._stats.recent_errors.copy(),
                error_rate_per_minute=self._stats.error_rate_per_minute,
                last_reset=self._stats.last_reset,
            )

    async def reset_stats(self) -> None:
        """Reset error statistics."""
        async with self._lock:
            self._stats = ErrorStats()


class RetryableErrorHandler(ErrorHandler):
    """Error handler that implements retry logic with exponential backoff."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    async def handle_error(self, error: EventBusError) -> bool:
        """Handle error with retry logic."""
        if not self._should_retry(error):
            return False

        retry_count = error.context.retry_count
        if retry_count >= self.max_retries:
            logger.warning(f"Max retries exceeded for error {error.context.error_id}")
            return False

        # Calculate delay with exponential backoff
        delay = min(
            self.base_delay * (self.backoff_factor**retry_count),
            self.max_delay,
        )

        logger.info(f"Retrying operation after {delay}s (attempt {retry_count + 1})")
        await asyncio.sleep(delay)

        error.context.retry_count += 1
        return True

    def _should_retry(self, error: EventBusError) -> bool:
        """Determine if error should be retried."""
        # Don't retry configuration errors
        if error.context.category == ErrorCategory.CONFIGURATION:
            return False

        # Don't retry validation errors
        if error.context.category == ErrorCategory.VALIDATION:
            return False

        # Don't retry critical errors
        if error.context.severity == ErrorSeverity.CRITICAL:
            return False

        return True


class CompositeErrorHandler(ErrorHandler):
    """Error handler that delegates to multiple handlers."""

    def __init__(self, handlers: list[ErrorHandler]) -> None:
        self.handlers = handlers

    async def handle_error(self, error: EventBusError) -> bool:
        """Handle error with all registered handlers."""
        results = []

        for handler in self.handlers:
            try:
                result = await handler.handle_error(error)
                results.append(result)
            except Exception as e:
                logger.error(f"Error handler {type(handler).__name__} failed: {e}")
                results.append(False)

        # Return True if at least one handler succeeded
        return any(results)


class ErrorManager:
    """Central error management system for EventBus."""

    def __init__(self) -> None:
        self._handlers: list[ErrorHandler] = []
        self._metrics_handler = MetricsErrorHandler()
        self._logging_handler = LoggingErrorHandler()

        # Add default handlers
        self.add_handler(self._metrics_handler)
        self.add_handler(self._logging_handler)

    def add_handler(self, handler: ErrorHandler) -> None:
        """Add an error handler."""
        self._handlers.append(handler)

    def remove_handler(self, handler: ErrorHandler) -> None:
        """Remove an error handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def handle_error(
        self,
        error: Exception | EventBusError,
        context: ErrorContext | None = None,
    ) -> bool:
        """
        Handle an error through all registered handlers.

        Args:
            error: The error to handle
            context: Additional context for the error

        Returns:
            True if error was handled successfully
        """
        # Convert regular exceptions to EventBusError
        if not isinstance(error, EventBusError):
            eventbus_error = EventBusError(
                message=str(error),
                context=context or ErrorContext(),
                cause=error,
            )
        else:
            eventbus_error = error

        # Process through all handlers
        results = []
        for handler in self._handlers:
            try:
                result = await handler.handle_error(eventbus_error)
                results.append(result)
            except Exception as e:
                logger.error(f"Error handler {type(handler).__name__} failed: {e}")
                results.append(False)

        return any(results)

    async def get_error_stats(self) -> ErrorStats:
        """Get error statistics."""
        return await self._metrics_handler.get_stats()

    async def reset_error_stats(self) -> None:
        """Reset error statistics."""
        await self._metrics_handler.reset_stats()


# Global error manager instance
error_manager = ErrorManager()


# Convenience functions for error handling
async def handle_error(
    error: Exception | EventBusError,
    context: ErrorContext | None = None,
) -> bool:
    """Handle an error using the global error manager."""
    return await error_manager.handle_error(error, context)


def create_error_context(
    category: ErrorCategory,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    component: str = "",
    operation: str = "",
    **metadata: Any,
) -> ErrorContext:
    """Create an error context with the specified parameters."""
    return ErrorContext(
        category=category,
        severity=severity,
        component=component,
        operation=operation,
        metadata=metadata,
    )


class error_boundary:
    """Decorator/context manager for error boundary handling."""

    def __init__(
        self,
        component: str,
        operation: str = "",
        category: ErrorCategory = ErrorCategory.PROCESSING,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        reraise: bool = True,
    ) -> None:
        self.component = component
        self.operation = operation
        self.category = category
        self.severity = severity
        self.reraise = reraise

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Use as decorator."""
        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with self:
                    return await func(*args, **kwargs)

            return async_wrapper

        def sync_wrapper(*args: Any, **kwargs: Any) -> None:
            with self:
                return

        return sync_wrapper

    async def __aenter__(self) -> "error_boundary":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Async context manager exit."""
        if exc_type is not None:
            context = create_error_context(
                category=self.category,
                severity=self.severity,
                component=self.component,
                operation=self.operation,
            )

            await handle_error(exc_val, context)

            if not self.reraise:
                return True  # Suppress exception

        return False

    def __enter__(self) -> "error_boundary":
        """Sync context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Sync context manager exit."""
        if exc_type is not None:
            context = create_error_context(
                category=self.category,
                severity=self.severity,
                component=self.component,
                operation=self.operation,
            )

            # For sync context, we handle the error synchronously
            # by using the logging handler directly
            try:
                eventbus_error = EventBusError(
                    message=str(exc_val),
                    context=context,
                    cause=exc_val,
                )

                # Use the global error manager's logging handler directly
                logging_handler = error_manager._logging_handler
                # Create a new event loop if none exists for the logging
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.create_task(logging_handler.handle_error(eventbus_error))
                except RuntimeError:
                    # No event loop running, handle synchronously
                    logger.error(
                        f"Error in {self.component}.{self.operation}: {exc_val}",
                        extra={
                            "error_id": context.error_id,
                            "category": context.category.value,
                            "severity": context.severity.value,
                            "component": context.component,
                            "operation": context.operation,
                        },
                    )
            except Exception as e:
                # Fallback logging
                logger.error(f"Failed to handle error in sync context: {e}")
                logger.error(f"Original error: {exc_val}")

            if not self.reraise:
                return True  # Suppress exception

        return False
