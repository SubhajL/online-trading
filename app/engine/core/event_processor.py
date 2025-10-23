"""
Event processor for handling event dispatch to subscriptions.
Separates event processing logic from subscription management.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.engine.core.subscription_manager import EventSubscription
from app.engine.models import BaseEvent
from app.engine.resilience.thread_safe_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)


@dataclass
class EventProcessingConfig:
    """Configuration for event processing."""

    max_processing_time_seconds: float = 30.0
    max_concurrent_handlers: int = 10
    enable_metrics: bool = True
    circuit_breaker_enabled: bool = True
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0


@dataclass
class EventProcessingError:
    """Error information for failed event processing."""

    subscription_id: str
    subscriber_id: str
    error_type: str
    error_message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class EventProcessingResult:
    """Result of processing an event."""

    event_id: UUID
    successful_handlers: int
    failed_handlers: int
    errors: list[EventProcessingError]
    processing_time: float


@dataclass
class EventProcessingStats:
    """Statistics for event processing."""

    events_processed: int = 0
    events_failed: int = 0
    successful_handlers: int = 0
    failed_handlers: int = 0
    total_processing_time: float = 0.0
    circuit_breaker_activations: int = 0

    @property
    def average_processing_time(self) -> float:
        """Calculate average processing time."""
        if self.events_processed == 0:
            return 0.0
        return self.total_processing_time / self.events_processed


class EventProcessingException(Exception):
    """Exception raised during event processing."""


class EventProcessor:
    """
    Processes events by dispatching them to subscriptions.

    Handles priority ordering, concurrency, timeouts, and error recovery
    with proper metrics tracking and circuit breaker protection.
    """

    def __init__(self, config: EventProcessingConfig | None = None):
        """Initialize event processor with optional config."""
        self._config = config or EventProcessingConfig()

        # Statistics tracking
        self._stats = EventProcessingStats()
        self._lock = asyncio.Lock()

        # Circuit breakers per subscriber
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

        # Semaphore for concurrency control
        self._concurrency_semaphore = asyncio.Semaphore(
            self._config.max_concurrent_handlers,
        )

    async def process_event(
        self,
        event: BaseEvent,
        subscriptions: list[EventSubscription],
    ) -> EventProcessingResult:
        """
        Process an event by dispatching to all relevant subscriptions.

        Uses bounded concurrency to run independent handlers in parallel,
        while preserving per-handler timeout and circuit breaker behavior.

        Args:
            event: The event to process
            subscriptions: list[Any] of subscriptions to dispatch to

        Returns:
            Processing result with success/failure counts and errors
        """
        start_time = asyncio.get_event_loop().time()
        errors: list[EventProcessingError] = []
        successful_handlers = 0
        failed_handlers = 0

        # Sort subscriptions by priority (highest first)
        sorted_subscriptions = sorted(
            subscriptions,
            key=lambda s: s.priority,
            reverse=True,
        )

        async def _run_single(
            subscription: EventSubscription,
        ) -> tuple[bool, EventSubscription, Exception | None]:
            """Run a single subscription with timeout + circuit breaker protection."""
            try:
                # Circuit breaker pre-check
                if self._config.circuit_breaker_enabled:
                    circuit_breaker = await self._get_circuit_breaker(
                        subscription.subscriber_id,
                    )
                    if not await circuit_breaker.should_allow_request():
                        return False, subscription, RuntimeError("CircuitBreakerOpen")

                # Process with semaphore + timeout
                await self._process_subscription(event, subscription)

                # Record success to circuit breaker
                if self._config.circuit_breaker_enabled:
                    circuit_breaker = await self._get_circuit_breaker(
                        subscription.subscriber_id,
                    )
                    await circuit_breaker.record_success()

                return True, subscription, None
            except Exception as exc:  # noqa: BLE001 - we reclassify below
                # Record failure to circuit breaker
                if self._config.circuit_breaker_enabled:
                    circuit_breaker = await self._get_circuit_breaker(
                        subscription.subscriber_id,
                    )
                    await circuit_breaker.record_failure()
                return False, subscription, exc

        # Build tasks for all active subscriptions; skip inactive immediately
        tasks: list[asyncio.Task[tuple[bool, EventSubscription, Exception | None]]] = []
        for sub in sorted_subscriptions:
            if not sub.is_active:
                continue
            tasks.append(asyncio.create_task(_run_single(sub)))

        # Execute concurrently and aggregate outcomes
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=False)
            for ok, sub, exc in results:
                if ok:
                    successful_handlers += 1
                else:
                    failed_handlers += 1
                    error_type = (
                        type(exc).__name__ if exc is not None else "ProcessingError"
                    )
                    error_message = str(exc) if exc is not None else "Unknown error"
                    # Normalize CB open case to a consistent type
                    if error_message == "CircuitBreakerOpen":
                        error_type = "CircuitBreakerOpen"
                    errors.append(
                        EventProcessingError(
                            subscription_id=sub.subscription_id,
                            subscriber_id=sub.subscriber_id,
                            error_type=error_type,
                            error_message=error_message,
                        ),
                    )

        processing_time = asyncio.get_event_loop().time() - start_time

        if self._config.enable_metrics:
            await self._update_stats(
                processing_time,
                successful_handlers,
                failed_handlers,
                len(errors) > 0,
            )

        return EventProcessingResult(
            event_id=event.event_id,
            successful_handlers=successful_handlers,
            failed_handlers=failed_handlers,
            errors=errors,
            processing_time=processing_time,
        )

    async def _process_subscription(
        self,
        event: BaseEvent,
        subscription: EventSubscription,
    ) -> None:
        """
        Process a single subscription with concurrency and timeout control.

        Args:
            event: The event to process
            subscription: The subscription to process

        Raises:
            asyncio.TimeoutError: If processing takes too long
            Exception: Any exception from the handler
        """
        async with self._concurrency_semaphore:
            # Apply timeout
            try:
                await asyncio.wait_for(
                    self._call_handler(event, subscription),
                    timeout=self._config.max_processing_time_seconds,
                )
            except TimeoutError:
                raise TimeoutError(
                    f"Handler timeout after {self._config.max_processing_time_seconds}s",
                )

    async def _call_handler(
        self,
        event: BaseEvent,
        subscription: EventSubscription,
    ) -> Any:
        """
        Call the subscription handler (async or sync).

        Args:
            event: The event to pass to the handler
            subscription: The subscription containing the handler

        Returns:
            Handler result
        """
        if asyncio.iscoroutinefunction(subscription.handler):
            return await subscription.handler(event)
        return subscription.handler(event)

    async def _get_circuit_breaker(self, subscriber_id: str) -> CircuitBreaker:
        """
        Get or create a circuit breaker for a subscriber.

        Args:
            subscriber_id: The subscriber identifier

        Returns:
            Circuit breaker instance
        """
        if subscriber_id not in self._circuit_breakers:
            cb_cfg = CircuitBreakerConfig(
                failure_threshold=self._config.failure_threshold,
                success_threshold=self._config.success_threshold,
                timeout_seconds=self._config.timeout_seconds,
            )
            self._circuit_breakers[subscriber_id] = CircuitBreaker(cb_cfg)

        return self._circuit_breakers[subscriber_id]

    async def _update_stats(
        self,
        processing_time: float,
        successful_handlers: int,
        failed_handlers: int,
        has_errors: bool,
    ) -> None:
        """
        Update processing statistics.

        Args:
            processing_time: Time taken to process the event
            successful_handlers: Number of successful handlers
            failed_handlers: Number of failed handlers
            has_errors: Whether there were any errors
        """
        async with self._lock:
            self._stats.events_processed += 1
            if has_errors:
                self._stats.events_failed += 1

            self._stats.successful_handlers += successful_handlers
            self._stats.failed_handlers += failed_handlers
            self._stats.total_processing_time += processing_time

            # Count circuit breaker activations
            if self._config.circuit_breaker_enabled:
                for circuit_breaker in self._circuit_breakers.values():
                    state = await circuit_breaker.get_state()
                    if state.name == "OPEN":
                        self._stats.circuit_breaker_activations += 1

    async def get_stats(self) -> EventProcessingStats:
        """Get current processing statistics."""
        async with self._lock:
            return EventProcessingStats(
                events_processed=self._stats.events_processed,
                events_failed=self._stats.events_failed,
                successful_handlers=self._stats.successful_handlers,
                failed_handlers=self._stats.failed_handlers,
                total_processing_time=self._stats.total_processing_time,
                circuit_breaker_activations=self._stats.circuit_breaker_activations,
            )

    async def reset_stats(self) -> None:
        """Reset all processing statistics."""
        async with self._lock:
            self._stats = EventProcessingStats()

    async def get_circuit_breaker_state(self, subscriber_id: str) -> str:
        """Get the circuit breaker state name for a subscriber."""
        cb = await self._get_circuit_breaker(subscriber_id)
        state = await cb.get_state()
        return state.name
